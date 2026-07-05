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
flag_emergency -- emergency trigger-pattern tool (tdd.md §5, confirmed §11)

The LLM DETECTS an active emergency (a natural-language judgment call) and
calls this tool; before_model_callback deterministically EXECUTES the
hang-up-and-call-000 redirect + end_session on the very next turn, checked
before slot-filling or out-of-scope routing (confirmed priority ordering,
tdd.md §11). This tool itself does nothing but set the flag -- it contains
zero redirect logic, matching the trigger pattern's LLM-decides-WHAT /
callback-decides-HOW split (gecx-design-guide.md -> "Callback Patterns for
Deterministic Behavior").

Always visible regardless of slot-filling state -- never hidden by
before_model_callback's tool-visibility logic.
"""


def flag_emergency() -> dict:
    """Signal that the caller's language indicates an active emergency or
    danger in progress (e.g. a fire currently burning, someone trapped or
    seriously injured right now, an ongoing assault or immediate threat to
    life or property). Call this immediately upon judging this to be true --
    do not wait for confirmation and do not continue the claim intake flow.

    Returns:
        dict: {"flagged": True, "agent_action": "Stop the claim intake flow
        immediately -- the platform will speak the emergency redirect and end
        the call on your next turn. Do not say anything else."}
    """
    context.state["_emergency_flag"] = True
    return {
        "flagged": True,
        "agent_action": (
            "Stop the claim intake flow immediately -- the platform will "
            "speak the emergency redirect and end the call on your next "
            "turn. Do not say anything else."
        ),
    }
