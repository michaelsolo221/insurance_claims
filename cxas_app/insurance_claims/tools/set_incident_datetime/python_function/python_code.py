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
set_incident_datetime -- FNOL slot setter (tdd.md §6, Slot-Filling DAG Framework)

Thin setter. The LLM is instructed to resolve relative wording ("yesterday
morning") to an absolute date/time using the current_date variable before
calling this tool -- this setter only validates the resulting string parses.
"""

import datetime


def set_incident_datetime(incident_datetime: str) -> dict:
    """Record the date and approximate time the incident occurred.

    Args:
        incident_datetime: The incident's date and time as "YYYY-MM-DD HH:MM"
            (24-hour clock) or "YYYY-MM-DD" if no time was given, already
            resolved from any relative wording using current_date (REQUIRED).

    Returns:
        dict: {"stored": True, "value": <incident_datetime>} on success, or
        {"error": True, "error_code": "invalid_format", "agent_action": <str>}
        if it doesn't parse.
    """
    raw = (incident_datetime or "").strip()
    draft = context.state.get("claim_notification_draft") or {}

    parsed = None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue

    if parsed is None:
        draft.setdefault("_slot_errors", []).append(
            {"slot": "incident_datetime", "code": "invalid_format"}
        )
        context.state["claim_notification_draft"] = draft
        return {
            "error": True,
            "error_code": "invalid_format",
            "agent_action": "The date/time given could not be parsed. Resolve any relative wording using current_date and ask the caller to confirm the date (and time, if known) again.",
        }

    slot = draft.setdefault("incident_datetime", {"value": "", "status": "unfilled", "attempts": 0})
    slot["value"] = raw
    slot["status"] = "pending"
    context.state["claim_notification_draft"] = draft
    return {"stored": True, "value": raw}
