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
set_policy_number -- FNOL slot setter (tdd.md §6, optional slot)

Optional slot: no attempts counter, no retry/orchestration logic. If the
caller doesn't have a policy number, the instruction tells the LLM not to
call this tool at all -- before_model_callback's orchestrator marks the slot
"not_captured" automatically after one unanswered ask (tdd.md §11: "a single
'don't know' ends collection for that slot immediately"). The only
validation this thin setter performs is rejecting a degenerate call with no
actual value, matching its own documented contract ("only call this tool
when the caller actually provides a number").
"""


def set_policy_number(policy_number: str) -> dict:
    """Record the caller's CGU policy number, if they have one.

    Args:
        policy_number: The policy number exactly as given by the caller
            (REQUIRED argument to this tool call -- only call this tool when
            the caller actually provides a number; this FNOL field itself is
            optional).

    Returns:
        dict: {"stored": True, "value": <policy_number>} on success, or
        {"error": True, "error_code": "empty_value", "agent_action": <str>}
        if called with no value.
    """
    value = (policy_number or "").strip()
    draft = context.state.get("claim_notification_draft") or {}

    if not value:
        draft.setdefault("_slot_errors", []).append(
            {"slot": "policy_number", "code": "empty_value"}
        )
        context.state["claim_notification_draft"] = draft
        return {
            "error": True,
            "error_code": "empty_value",
            "agent_action": "This tool should only be called when the caller provides an actual policy number. Do not call it again for this field unless they give one.",
        }

    slot = draft.setdefault("policy_number", {"value": "", "status": "unfilled"})
    slot["value"] = value
    slot["status"] = "pending"
    context.state["claim_notification_draft"] = draft
    return {"stored": True, "value": value}
