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
set_hazard_flag -- FNOL slot setter (tdd.md §6, Slot-Filling DAG Framework)

Thin setter: a boolean flag has no format to validate -- the only error case
is the argument being missing entirely (a malformed tool call), which is
rejected rather than silently coerced.

NOTE: this is a DATA FIELD for the claims record (is there an ongoing hazard
at the scene, e.g. a downed power line), distinct from the flag_emergency
tool, which pre-empts and ends the ENTIRE call for an active, in-progress
emergency (tdd.md §5). Do not conflate the two -- flag_emergency's priority
and end-the-call behavior are unrelated to this slot.
"""


def set_hazard_flag(hazard_present: bool) -> dict:
    """Record whether there is an ongoing hazard at the scene of the incident.

    Args:
        hazard_present: True if the caller indicates an ongoing hazard or
            safety risk to others at the scene, False otherwise (REQUIRED).

    Returns:
        dict: {"stored": True, "value": <hazard_present>} on success, or
        {"error": True, "error_code": "missing_value", "agent_action": <str>}
        if the argument was not supplied.
    """
    if hazard_present is None:
        draft = context.state.get("claim_notification_draft") or {}
        draft.setdefault("_slot_errors", []).append(
            {"slot": "hazard_flag", "code": "missing_value"}
        )
        context.state["claim_notification_draft"] = draft
        return {
            "error": True,
            "error_code": "missing_value",
            "agent_action": "No yes/no answer was captured. Ask the caller whether there is an ongoing hazard at the scene again.",
        }

    draft = context.state.get("claim_notification_draft") or {}
    slot = draft.setdefault("hazard_flag", {"value": "", "status": "unfilled", "attempts": 0})
    slot["value"] = bool(hazard_present)
    slot["status"] = "pending"
    context.state["claim_notification_draft"] = draft
    return {"stored": True, "value": bool(hazard_present)}
