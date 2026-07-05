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
set_incident_description -- FNOL slot setter (tdd.md §6, Slot-Filling DAG Framework)

Thin setter: validates non-empty, writes to `pending`, signals errors via
_slot_errors, and returns.
"""


def set_incident_description(incident_description: str) -> dict:
    """Record a description of what happened in the incident.

    Args:
        incident_description: A summary of what happened, in the caller's own
            words (REQUIRED).

    Returns:
        dict: {"stored": True, "value": <incident_description>} on success, or
        {"error": True, "error_code": "empty_value", "agent_action": <str>} if
        empty.
    """
    value = (incident_description or "").strip()
    draft = context.state.get("claim_notification_draft") or {}

    if not value:
        draft.setdefault("_slot_errors", []).append(
            {"slot": "incident_description", "code": "empty_value"}
        )
        context.state["claim_notification_draft"] = draft
        return {
            "error": True,
            "error_code": "empty_value",
            "agent_action": "No description was captured. Ask the caller what happened again.",
        }

    slot = draft.setdefault("incident_description", {"value": "", "status": "unfilled", "attempts": 0})
    slot["value"] = value
    slot["status"] = "pending"
    context.state["claim_notification_draft"] = draft
    return {"stored": True, "value": value}
