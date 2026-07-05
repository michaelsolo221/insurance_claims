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
set_callback_phone -- FNOL slot setter (tdd.md §6/§12, Slot-Filling DAG Framework)

Thin setter. Also the correction path for the telephony-caller-id pre-fill:
before_model_callback initializes this slot's value from the ANI session
parameter with status "pending" when present (tdd.md §12) -- this tool
overwrites that value (still writing to "pending") if the caller gives a
different number during the read-back.
"""


def set_callback_phone(phone_number: str) -> dict:
    """Record the best callback phone number for the claim.

    Args:
        phone_number: The caller's callback phone number (digits, spaces, and
            standard separators, e.g. "0412 345 678") (REQUIRED).

    Returns:
        dict: {"stored": True, "value": <phone_number>} on success, or
        {"error": True, "error_code": "invalid_format", "agent_action": <str>}
        if it doesn't contain enough digits to plausibly be a phone number.
    """
    raw = (phone_number or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    draft = context.state.get("claim_notification_draft") or {}

    if len(digits) < 8:
        draft.setdefault("_slot_errors", []).append(
            {"slot": "callback_phone", "code": "invalid_format"}
        )
        context.state["claim_notification_draft"] = draft
        return {
            "error": True,
            "error_code": "invalid_format",
            "agent_action": "The number given doesn't have enough digits to be a valid callback number. Ask the caller to repeat their best callback number.",
        }

    slot = draft.setdefault("callback_phone", {"value": "", "status": "unfilled", "attempts": 0})
    slot["value"] = raw
    slot["status"] = "pending"
    context.state["claim_notification_draft"] = draft
    return {"stored": True, "value": raw}
