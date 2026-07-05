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
set_caller_name -- FNOL slot setter (tdd.md §6, Slot-Filling DAG Framework)

Thin setter: validates the input is non-empty, writes to `pending` on the
consolidated claim_notification_draft state variable, signals errors via
_slot_errors, and returns. Zero DAG logic, zero control flow, zero knowledge
of other slots (gecx-design-guide.md -> "Slot Filling Framework" -> "Setters
are thin"). before_model_callback's orchestrator (_run_slot_filling) decides
what happens next.
"""


def set_caller_name(caller_name: str) -> dict:
    """Record the caller's full name for the claim notification.

    Args:
        caller_name: The caller's full name, exactly as given (REQUIRED).

    Returns:
        dict: {"stored": True, "value": <name>} on success, or
        {"error": True, "error_code": "empty_value", "agent_action": <str>} if
        no name was captured.
    """
    name = (caller_name or "").strip()
    draft = context.state.get("claim_notification_draft") or {}

    if not name:
        draft.setdefault("_slot_errors", []).append(
            {"slot": "caller_name", "code": "empty_value"}
        )
        context.state["claim_notification_draft"] = draft
        return {
            "error": True,
            "error_code": "empty_value",
            "agent_action": "No name was captured. Ask the caller for their full name again.",
        }

    slot = draft.setdefault("caller_name", {"value": "", "status": "unfilled", "attempts": 0})
    slot["value"] = name
    slot["status"] = "pending"
    context.state["claim_notification_draft"] = draft
    return {"stored": True, "value": name}
