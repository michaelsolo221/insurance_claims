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
set_injury_flag -- FNOL slot setter (tdd.md §6, Slot-Filling DAG Framework)

Thin setter: a boolean flag has no format to validate -- the only error case
is the argument being missing entirely (a malformed tool call), which is
rejected rather than silently coerced. Zero DAG logic, zero control flow.
"""


def set_injury_flag(injury_occurred: bool) -> dict:
    """Record whether anyone was injured in the incident.

    Args:
        injury_occurred: True if the caller indicates anyone was injured,
            False if the caller indicates no injuries occurred (REQUIRED).

    Returns:
        dict: {"stored": True, "value": <injury_occurred>} on success, or
        {"error": True, "error_code": "missing_value", "agent_action": <str>}
        if the argument was not supplied.
    """
    if injury_occurred is None:
        draft = context.state.get("claim_notification_draft") or {}
        draft.setdefault("_slot_errors", []).append(
            {"slot": "injury_flag", "code": "missing_value"}
        )
        context.state["claim_notification_draft"] = draft
        return {
            "error": True,
            "error_code": "missing_value",
            "agent_action": "No yes/no answer was captured. Ask the caller whether anyone was injured again.",
        }

    draft = context.state.get("claim_notification_draft") or {}
    slot = draft.setdefault("injury_flag", {"value": "", "status": "unfilled", "attempts": 0})
    slot["value"] = bool(injury_occurred)
    slot["status"] = "pending"
    context.state["claim_notification_draft"] = draft
    return {"stored": True, "value": bool(injury_occurred)}
