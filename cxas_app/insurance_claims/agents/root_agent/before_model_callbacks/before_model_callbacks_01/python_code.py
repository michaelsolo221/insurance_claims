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
before_model_callback -- root_agent (insurance_claims)

PURPOSE (tdd.md Architecture -- "Field-collection implementation: Slot-Filling
DAG Framework"):
    Implements the confirmed Slot-Filling DAG Framework for the 9 FNOL fields,
    split three ways in this single file per the design guide's convention:

    1. _get_config()             -- agent-specific slot definitions (tdd.md §6),
                                     the single backend task, and the confirmed
                                     retry policy (tdd.md §11).
    2. _run_slot_filling()        -- CES-agnostic orchestrator. Takes
                                     (config, sm), mutates sm in place, returns
                                     an action dict. Never touches CES types --
                                     testable with plain dicts.
    3. before_model_callback()    -- thin CES adapter (~20 lines of actual
                                     adapter logic below the greeting/emergency
                                     checks): applies tool visibility, injects
                                     _system_message, and handles the two
                                     higher-priority preemptions (greeting,
                                     emergency) ahead of slot-filling.

PRIORITY ORDER ON EVERY TURN (tdd.md §11, confirmed):
    1. Deterministic greeting (first turn only).
    2. Emergency preemption (_emergency_flag) -- ALWAYS checked before
       slot-filling or out-of-scope routing.
    3. Slot-filling orchestration.

    Out-of-scope decline/redirect is NOT handled here -- it is a
    natural-language judgment call handled by the LLM per instruction.txt,
    per tdd.md Routing Logic.

WHY NOT A SEPARATE after_tool_callback:
    tdd.md describes the setter tools as writing directly to the consolidated
    `claim_notification_draft` state variable ("each validates its input,
    writes to pending... and returns" -- zero DAG logic, zero control flow).
    This scaffold has setters write directly via the `context` global rather
    than routing through an intermediate after_tool_callback layer, matching
    the simpler 3-piece framework tdd.md commits to (not the more elaborate
    production variant documented in examples/bella_notte, which splits setter
    result-routing into its own after_tool_callback).

PLATFORM GLOBALS (do NOT import these):
    CallbackContext, Content, Part, LlmResponse, LlmRequest are auto-provided
    by the GECX sandbox at runtime. Only standard library imports need
    explicit import statements.
"""

from typing import Optional


# =============================================================================
# 1. _get_config() -- agent-specific Slot-Filling config (tdd.md §6, §11)
# =============================================================================

def _get_config() -> dict:
    """FNOL slot definitions, ask prompts, and the confirmed retry policy.

    Replace this function if the FNOL field list changes -- _run_slot_filling()
    below is agent-agnostic and should not need edits.
    """
    return {
        "slots": [
            {"name": "caller_name", "required": True,
             "ask": "Could I get your full name, please?"},
            {"name": "callback_phone", "required": True,
             "ask": "What's the best phone number to reach you on?"},
            {"name": "policy_number", "required": False,
             "ask": "Do you have your CGU policy number handy? That's fine to skip if you don't have it."},
            {"name": "incident_datetime", "required": True,
             "ask": "When did the incident happen -- the date and approximate time?"},
            {"name": "incident_location", "required": True,
             "ask": "Where did the incident happen?"},
            {"name": "incident_description", "required": True,
             "ask": "Can you tell me what happened?"},
            {"name": "injury_flag", "required": True,
             "ask": "Was anyone injured?"},
            {"name": "hazard_flag", "required": True,
             "ask": "Is there an ongoing hazard at the scene right now, like a safety risk to others?"},
            {"name": "callback_window", "required": False,
             "ask": "Is there a particular time of day that's best for us to call you back? That's optional."},
        ],
        # Confirmed retry policy (tdd.md §11): retry up to 2 additional times
        # (3 total attempts) for REQUIRED slots only. Optional slots get a
        # single ask -- one non-answer ends collection for that slot
        # immediately, no attempts counter.
        "max_attempts": 3,
        "submit_tool": "submit_claim_notification",
    }


# Slot name -> setter tool name (tdd.md Tools table).
_SETTERS = {
    "caller_name": "set_caller_name",
    "callback_phone": "set_callback_phone",
    "policy_number": "set_policy_number",
    "incident_datetime": "set_incident_datetime",
    "incident_location": "set_incident_location",
    "incident_description": "set_incident_description",
    "injury_flag": "set_injury_flag",
    "hazard_flag": "set_hazard_flag",
    "callback_window": "set_callback_window",
}

# Slot name -> human-readable label used in the readback recap.
_READBACK_LABELS = {
    "caller_name": "your name",
    "callback_phone": "the callback number",
    "policy_number": "your policy number",
    "incident_datetime": "when it happened",
    "incident_location": "where it happened",
    "incident_description": "what happened",
    "injury_flag": "whether anyone was injured",
    "hazard_flag": "whether there's an ongoing hazard",
    "callback_window": "your preferred callback time",
}

# Short, non-exhaustive affirmative/correction word lists used ONLY to detect
# confirmation of the readback recap -- NOT for broad intent classification.
# (gecx-design-guide.md warns against hardcoded phrase lists for INTENT
# DETECTION; this is the narrower, well-precedented yes/no-confirmation
# pattern also used by the platform's own Slot-Filling reference
# implementation's `_is_affirmative` helper.)
_AFFIRMATIVE_STARTERS = frozenset({
    "yes", "yeah", "yep", "yup", "correct", "right", "sure", "ok", "okay",
    "perfect", "great", "exactly", "confirmed", "absolutely", "good",
})
_CORRECTION_SIGNALS = frozenset({
    "but", "actually", "wait", "change", "not", "no", "wrong", "instead", "different",
})
_STRIP_PUNCT = str.maketrans("", "", ".,;:!?\"'")

# Setter-signaled validation errors (tdd.md: setters "signal errors via
# _slot_errors" -- this scaffold has setters append directly to the
# claim_notification_draft's _slot_errors list since there is no separate
# after_tool_callback in this simpler, single-callback-file design).
_SLOT_ERROR_MESSAGES = {
    ("callback_phone", "invalid_format"):
        "That doesn't look like a complete phone number -- could you say it again, including the area code?",
    ("incident_datetime", "invalid_format"):
        "I didn't quite catch a valid date and time -- could you tell me again when the incident happened?",
    ("caller_name", "empty_value"):
        "Sorry, I didn't catch a name there -- could you tell me your full name again?",
    ("incident_location", "empty_value"):
        "Sorry, I didn't catch that -- where did the incident happen?",
    ("incident_description", "empty_value"):
        "Sorry, could you describe again what happened?",
}


def _is_affirmative(text: str) -> bool:
    """True if `text` is a short, unqualified confirmation of the readback."""
    normalized = (text or "").lower().strip()
    if not normalized:
        return False
    words = [w.translate(_STRIP_PUNCT) for w in normalized.split()]
    if not words:
        return False
    if len(words) > 6:
        return False
    if words[0] not in _AFFIRMATIVE_STARTERS:
        return False
    return not any(w in _CORRECTION_SIGNALS for w in words[1:])


def _default_draft() -> dict:
    """Fallback default matching app.json's claim_notification_draft schema.

    Used only defensively -- the platform initializes session state from the
    declared variable default on session start, so this should rarely (if
    ever) be exercised in practice.
    """
    required = ["caller_name", "callback_phone", "incident_datetime",
                "incident_location", "incident_description", "injury_flag",
                "hazard_flag"]
    optional = ["policy_number", "callback_window"]
    draft = {}
    for name in required:
        draft[name] = {"value": "", "status": "unfilled", "attempts": 0}
    for name in optional:
        draft[name] = {"value": "", "status": "unfilled"}
    draft["readback_confirmed"] = False
    draft["_last_asked_slot"] = ""
    draft["_awaiting_readback_response"] = False
    return draft


def _compute_hidden_tools(config: dict, sm: dict, phase: str) -> list:
    """Per-turn tool visibility -- the PRIMARY correctness mechanism for this
    Slot-Filling agent (design guide's documented exception to the general
    "don't overuse hide_tool()" guidance). flag_emergency is intentionally
    NEVER included here -- tdd.md requires it stay visible at all times."""
    hide = []
    if phase == "collection":
        # Hide setters for slots already resolved (pending/confirmed/
        # not_captured) -- re-setting them would corrupt state.
        for name, tool in _SETTERS.items():
            if sm[name]["status"] != "unfilled":
                hide.append(tool)
        hide.append(config["submit_tool"])
    elif phase == "readback":
        # All setters stay visible so the caller can inline-correct any value
        # while the recap is being confirmed. Only submission stays hidden.
        hide.append(config["submit_tool"])
    else:  # phase == "submit"
        hide.extend(_SETTERS.values())
    return hide


def _build_readback_message(config: dict, sm: dict) -> str:
    """Build the directive that tells the LLM what to read back (tdd.md:
    'should read back the captured details... for confirmation before
    submitting')."""
    parts = []
    for slot in config["slots"]:
        name = slot["name"]
        status = sm[name]["status"]
        label = _READBACK_LABELS.get(name, name)
        if status in ("pending", "confirmed"):
            parts.append(f"{label}: {sm[name]['value']}")
        elif status == "not_captured":
            parts.append(f"{label}: not captured")
    joined = "; ".join(parts)
    return (
        "Read back ALL of the following captured details together in one "
        f"recap and ask the caller to confirm they are correct: {joined}."
    )


# =============================================================================
# 2. _run_slot_filling(config, sm) -- CES-agnostic orchestrator
# =============================================================================

def _run_slot_filling(config: dict, sm: dict) -> dict:
    """Advance `sm` (the claim_notification_draft dict) by one step and return
    an action dict: {"hide_tools": [...], "message": str, "ready_to_submit": bool}.

    Reads and clears the transient keys `_new_turn`, `_caller_id`, and
    `_last_user_text` that before_model_callback stashes into `sm` before
    calling this function -- these never persist into the stored state.
    """
    slots_cfg = {s["name"]: s for s in config["slots"]}
    max_attempts = config["max_attempts"]

    new_turn = bool(sm.pop("_new_turn", False))
    caller_id = sm.pop("_caller_id", "")
    last_user_text = sm.pop("_last_user_text", "")

    # ---- Validation errors signaled by a setter this turn (tdd.md: setters
    # "signal errors via _slot_errors") -- surface the most recent one as a
    # deterministic nudge. Does not count as a retry attempt; the caller gets
    # an unpenalized retry on the same slot. -----------------------------
    slot_errors = sm.pop("_slot_errors", [])
    if slot_errors:
        error = slot_errors[-1]
        message = _SLOT_ERROR_MESSAGES.get(
            (error.get("slot"), error.get("code")),
            "Sorry, I didn't quite catch that -- could you say that again?",
        )
        return {"hide_tools": [config["submit_tool"]], "message": message, "ready_to_submit": False}

    # ---- One-time pre-fill of callback_phone from telephony-caller-id ------
    # (tdd.md §12: pre-fill with status "pending" so the orchestrator routes
    # straight to read-back/confirmation instead of a cold ask.)
    if caller_id and sm["callback_phone"]["status"] == "unfilled" and not sm["callback_phone"]["value"]:
        sm["callback_phone"]["value"] = caller_id
        sm["callback_phone"]["status"] = "pending"

    # ---- Retry-attempt tracking for the slot asked last turn ---------------
    # (tdd.md §11: retry up to 2 additional times -- 3 total attempts -- for
    # required slots; optional slots get a single ask.)
    last_asked = sm.get("_last_asked_slot", "")
    if new_turn and last_asked and last_asked in slots_cfg and sm[last_asked]["status"] == "unfilled":
        if slots_cfg[last_asked]["required"]:
            sm[last_asked]["attempts"] = int(sm[last_asked].get("attempts", 0)) + 1
            if sm[last_asked]["attempts"] >= max_attempts:
                sm[last_asked]["status"] = "not_captured"
        else:
            sm[last_asked]["status"] = "not_captured"

    # ---- If a correction landed after confirmation, re-open the readback ---
    if sm.get("readback_confirmed") and any(
        sm[name]["status"] == "pending" for name in slots_cfg
    ):
        sm["readback_confirmed"] = False
        sm["_awaiting_readback_response"] = False

    all_resolved = all(sm[name]["status"] != "unfilled" for name in slots_cfg)


    # ---- callback_phone pre-fill confirmation (tdd.md §12) ------------------
    # When callback_phone was pre-filled from telephony-caller-id (status
    # "pending"), confirm it before collecting any other fields. A caller's
    # spoken "yes" promotes it to "confirmed" immediately so slot-filling can
    # move on to the next unfilled slot -- not deferred to the Phase 2
    # all-slots readback.
    if sm["callback_phone"]["status"] == "pending":
        if new_turn and last_asked == "callback_phone" and _is_affirmative(last_user_text):
            sm["callback_phone"]["status"] = "confirmed"
            # Fall through to normal Phase 1 collection below -- callback_phone
            # is now "confirmed", so next_slot will be the first actually-
            # unfilled required slot.
        else:
            sm["_last_asked_slot"] = "callback_phone"
            hide = _compute_hidden_tools(config, sm, phase="collection")
            # Re-show the callback_phone setter so the caller can correct the
            # pre-filled number inline (tdd.md §12: "caller can still correct
            # it via a normal set_callback_phone call").
            if "set_callback_phone" in hide:
                hide.remove("set_callback_phone")
            message = (
                "Ask the caller to confirm the callback number on file: "
                f"{sm['callback_phone']['value']}. If they give a different "
                "number, use it instead."
            )
            return {"hide_tools": hide, "message": message, "ready_to_submit": False}

    # ---- Phase 1: collection -----------------------------------------------
    if not all_resolved:
        next_slot = next(
            (s["name"] for s in config["slots"] if sm[s["name"]]["status"] == "unfilled"),
            None,
        )
        sm["_last_asked_slot"] = next_slot or ""
        hide = _compute_hidden_tools(config, sm, phase="collection")
        message = slots_cfg[next_slot]["ask"] if next_slot else "Let's move on."
        return {"hide_tools": hide, "message": message, "ready_to_submit": False}

    # ---- Phase 2: readback ---------------------------------------------------
    if not sm.get("readback_confirmed", False):
        has_pending = any(sm[name]["status"] == "pending" for name in slots_cfg)
        if has_pending:
            if new_turn and sm.get("_awaiting_readback_response") and _is_affirmative(last_user_text):
                for name in slots_cfg:
                    if sm[name]["status"] == "pending":
                        sm[name]["status"] = "confirmed"
                sm["readback_confirmed"] = True
                sm["_awaiting_readback_response"] = False
                hide = _compute_hidden_tools(config, sm, phase="submit")
                return {"hide_tools": hide, "message": "Thank you for confirming those details.", "ready_to_submit": True}

            sm["_awaiting_readback_response"] = True
            hide = _compute_hidden_tools(config, sm, phase="readback")
            message = _build_readback_message(config, sm)
            return {"hide_tools": hide, "message": message, "ready_to_submit": False}
        else:
            # Nothing left in "pending" (e.g. every remaining slot ended up
            # not_captured) -- nothing to confirm, proceed to submission.
            sm["readback_confirmed"] = True
            sm["_awaiting_readback_response"] = False

    # ---- Phase 3: ready to submit -------------------------------------------
    hide = _compute_hidden_tools(config, sm, phase="submit")
    return {"hide_tools": hide, "message": "", "ready_to_submit": True}


# =============================================================================
# 3. before_model_callback() -- thin CES adapter
# =============================================================================

def before_model_callback(callback_context: CallbackContext, llm_request: LlmRequest) -> Optional[LlmResponse]:
    state = callback_context.state

    # -------------------------------------------------------------------
    # PRIORITY 1: Deterministic greeting (tdd.md §12) -- fixed opening line
    # evaluated before any other routing branch, every call.
    # -------------------------------------------------------------------
    for part in callback_context.get_last_user_input():
        if part.text == "<event>session start</event>":
            greeting = (
                "Good day, you've reached CGU express claim lodgements, "
                "my name is Amanda, how can I help you?"
            )
            return LlmResponse.from_parts(parts=[Part.from_text(text=greeting)])

    # -------------------------------------------------------------------
    # PRIORITY 2: Emergency preemption -- checked before slot-filling and
    # before out-of-scope routing, on EVERY turn (confirmed priority
    # ordering, tdd.md §11).
    # -------------------------------------------------------------------
    emergency_flag = state.get("_emergency_flag", False)
    if isinstance(emergency_flag, str):
        emergency_flag = emergency_flag.strip().lower() == "true"
    if emergency_flag:
        state["_emergency_flag"] = False  # clear to prevent re-firing
        return LlmResponse.from_parts(parts=[
            Part.from_text(
                text="This sounds like an emergency. Please hang up now and call 000 immediately."
            ),
            Part.from_function_call(name="end_session", args={"session_escalated": True}),
        ])

    # -------------------------------------------------------------------
    # PRIORITY 3: Slot-filling orchestration. Out-of-scope decline/redirect
    # is a natural-language judgment call left to the LLM (instruction.txt) --
    # not intercepted here.
    # -------------------------------------------------------------------
    config = _get_config()
    sm = state.get("claim_notification_draft") or _default_draft()

    last_user_text = ""
    contents = llm_request.contents
    if contents:
        last_content = contents[-1]
        if last_content.role == "user":
            for part in last_content.parts:
                text = part.text_or_transcript()
                if text:
                    last_user_text = text
                    break

    sm["_new_turn"] = bool(last_user_text)
    sm["_caller_id"] = state.get("telephony-caller-id", "")
    sm["_last_user_text"] = last_user_text

    action = _run_slot_filling(config, sm)

    state["claim_notification_draft"] = sm
    state["_system_message"] = action["message"]

    for tool_name in action["hide_tools"]:
        llm_request.config.hide_tool(tool_name)

    return None
