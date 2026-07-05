# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
after_model_callback -- root_agent (insurance_claims)

PURPOSE (tdd.md Callbacks, revised §12):
    Deterministic submission-outcome acknowledgment. Once submit_claim_notification
    resolves, ensure the caller hears an explicit outcome message rather than
    relying on the LLM to remember to speak before calling end_session (the
    same LLM-forgets-to-speak-before-escalating failure mode the design guide
    documents for farewells generally).

    The gating condition is the FIRESTORE WRITE outcome, NOT the async Gmail
    send (§12) -- the Cloud Task/Cloud Function email hand-off happens after
    the call has already ended and is never observable on the live call path.

    - Firestore write SUCCESS: speak a success acknowledgment and call
      end_session. Handled entirely here -- no further LLM action needed.
    - Firestore write FAILURE: speak the deterministic apology, but do NOT
      call end_session here. submit_claim_notification's own return value
      carries an `agent_action` instruction (per gecx-design-guide.md ->
      Error Handling Guidelines) telling the LLM to take/confirm a callback
      number before ending the call -- that follow-up conversation needs LLM
      judgment and can't be preempted in one shot. instruction.txt's
      Submission_Failure_Fallback step carries the caller through that.

WHY THIS IS after_model_callback, NOT after_tool_callback:
    tdd.md's Callbacks table explicitly names this callback (not an
    after_tool_callback) as the mechanism for the acknowledgment. It works by
    walking `callback_context.events` for the most recent
    submit_claim_notification function response, the same event-history-walk
    pattern the template's after_model_callback uses to avoid double-texting
    across a multi-model-call turn.

    NOTE: reading a specific tool's function_response from event history
    inside after_model_callback (rather than after_tool_callback) is not
    directly demonstrated in the bundled reference examples -- verify
    `part.function_response` shape against the real platform at push/lint
    time (see this scaffold's manifest `unresolved` list).

PLATFORM GLOBALS (do NOT import these):
    CallbackContext, Content, Part, LlmResponse, LlmRequest are auto-provided
    by the GECX sandbox at runtime. Only standard library imports need
    explicit import statements.
"""

from typing import Optional

SUCCESS_MESSAGE = (
    "Thank you, your claim notification has been lodged. A CGU claims "
    "consultant will follow up with you soon. Take care."
)
FAILURE_MESSAGE = (
    "I'm sorry, I wasn't able to lodge your claim notification just now due "
    "to a system issue on our end."
)


def _find_submit_result(callback_context: CallbackContext) -> Optional[dict]:
    """Walk event history backwards for the most recent
    submit_claim_notification function response within the current turn
    (stop scanning once we reach the last user event)."""
    for event in reversed(callback_context.events):
        if event.is_user():
            break
        for part in event.parts():
            response = part.function_response
            if response is not None and getattr(response, "name", "") == "submit_claim_notification":
                return getattr(response, "response", None) or {}
    return None


def after_model_callback(callback_context: CallbackContext, llm_response: LlmResponse) -> Optional[LlmResponse]:
    state = callback_context.state

    # -------------------------------------------------------------------
    # STEP 1: Only relevant once submit_claim_notification has resolved.
    # -------------------------------------------------------------------
    result = _find_submit_result(callback_context)
    if result is None:
        return None

    # -------------------------------------------------------------------
    # STEP 2: Only acknowledge once per submission -- guards against
    # re-injecting the message on later model calls within the same
    # (multi-model-call) turn, or on subsequent turns during the failure
    # fallback conversation.
    # -------------------------------------------------------------------
    if str(state.get("_submission_acknowledged", "false")).lower() == "true":
        return None

    # -------------------------------------------------------------------
    # STEP 3: If the LLM already produced text in THIS model call, don't
    # double-text -- same multi-model-call guard as the template's
    # after_model_callback.
    # -------------------------------------------------------------------
    has_text_this_call = any(
        (part.text_or_transcript() or "").strip()
        for part in llm_response.content.parts
    )
    if has_text_this_call:
        return None

    state["_submission_acknowledged"] = "true"

    firestore_write_succeeded = bool(result.get("success"))

    if firestore_write_succeeded:
        return LlmResponse.from_parts(parts=[
            Part.from_text(text=SUCCESS_MESSAGE),
            Part.from_function_call(name="end_session", args={"session_escalated": False}),
        ])

    # Firestore write failed: speak the deterministic apology only.
    # Do NOT call end_session here -- the LLM follows submit_claim_notification's
    # own `agent_action` guidance (and instruction.txt's
    # Submission_Failure_Fallback step) to take/confirm a callback number
    # before ending the call.
    return LlmResponse.from_parts(parts=[
        Part.from_text(text=FAILURE_MESSAGE),
    ])
