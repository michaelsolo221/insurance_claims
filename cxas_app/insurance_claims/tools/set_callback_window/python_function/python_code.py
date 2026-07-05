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
set_callback_window -- FNOL slot setter (tdd.md §6, optional slot)

Optional slot: no attempts counter, no retry/orchestration logic. If the
caller has no preference, the instruction tells the LLM not to call this
tool at all -- before_model_callback's orchestrator marks the slot
"not_captured" automatically after one unanswered ask (tdd.md §11). The only
validation this thin setter performs is rejecting a degenerate call with no
actual value, matching its own documented contract ("only call this tool
when the caller actually volunteers a preference").
"""


def set_callback_window(callback_window: str) -> dict:
    """Record the caller's preferred time window for a callback, if given.

    Args:
        callback_window: A description of the preferred callback time (e.g.
            "weekday mornings", "after 5pm") (REQUIRED argument to this tool
            call -- only call this tool when the caller actually volunteers a
            preference; this FNOL field itself is optional).

    Returns:
        dict: {"stored": True, "value": <callback_window>} on success, or
        {"error": True, "error_code": "empty_value", "agent_action": <str>}
        if called with no value.
    """
    value = (callback_window or "").strip()
    draft = context.state.get("claim_notification_draft") or {}

    if not value:
        draft.setdefault("_slot_errors", []).append(
            {"slot": "callback_window", "code": "empty_value"}
        )
        context.state["claim_notification_draft"] = draft
        return {
            "error": True,
            "error_code": "empty_value",
            "agent_action": "This tool should only be called when the caller volunteers a callback time preference. Do not call it again for this field unless they give one.",
        }

    slot = draft.setdefault("callback_window", {"value": "", "status": "unfilled"})
    slot["value"] = value
    slot["status"] = "pending"
    context.state["claim_notification_draft"] = draft
    return {"stored": True, "value": value}
