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
submit_claim_notification -- two-step FNOL submission tool (tdd.md §12 redesign)

STEP 1 (synchronous, call-blocking): write the full claim record to Firestore.
    This is the ONLY operation the live call waits on -- the tool's return
    value reflects ONLY this outcome (tdd.md §12).
STEP 2 (async, fire-and-forget from the live call's perspective): enqueue a
    Cloud Task that triggers a separate Cloud Function (provisioned
    separately via Terraform in infra/ -- NOT a CES tool) to send the
    confirmation email via Gmail API after the call has already ended. A
    failure in this step is an infrastructure-level concern, not a
    caller-facing one -- the Firestore record is already durable (tdd.md §12
    Error Handling note). It does NOT change this tool's return value.

INFRA IDENTIFIERS (from infra/ Terraform outputs -- resource identifiers only,
not secrets):
    - GCP project:           graphic-tide-501406-p2
    - Firestore database ID: insurance-claims-fnol
    - Firestore collection:  claim_notifications
    - Cloud Tasks queue:     projects/graphic-tide-501406-p2/locations/us-central1/queues/claim-email-dispatch
    - Async email function:  https://us-central1-graphic-tide-501406-p2.cloudfunctions.net/send-claim-email
    - Service account:       insurance-claims-agent@graphic-tide-501406-p2.iam.gserviceaccount.com

OPEN QUESTION (tdd.md Known Issues -- flagged there, not yet resolved by any
source, carried into this scaffold's manifest `unresolved` list): the exact
Firestore document schema beyond the claim_notification_draft slot values,
and the exact Cloud Tasks HTTP request/body shape the send-claim-email Cloud
Function expects, are not specified. This stub writes the slot values
directly as the Firestore document body and enqueues a minimal JSON payload
(claim_id + collection + database) for the Cloud Function to re-read the
full record from Firestore. Confirm/adjust once the Cloud Function's
expected payload is finalized -- do not treat this as load-bearing without
that confirmation.
"""

import datetime
import uuid

_PROJECT_ID = "graphic-tide-501406-p2"
_FIRESTORE_DATABASE = "insurance-claims-fnol"
_FIRESTORE_COLLECTION = "claim_notifications"
_CLOUD_TASKS_QUEUE = "projects/graphic-tide-501406-p2/locations/us-central1/queues/claim-email-dispatch"
_EMAIL_FUNCTION_URI = "https://us-central1-graphic-tide-501406-p2.cloudfunctions.net/send-claim-email"
_SERVICE_ACCOUNT = "insurance-claims-agent@graphic-tide-501406-p2.iam.gserviceaccount.com"

_SLOT_NAMES = (
    "caller_name", "callback_phone", "policy_number", "incident_datetime",
    "incident_location", "incident_description", "injury_flag",
    "hazard_flag", "callback_window",
)


def submit_claim_notification() -> dict:
    """Submit the completed FNOL claim notification.

    Only call this once all required fields have been captured (or marked
    "not_captured" after retry exhaustion) and the caller has confirmed the
    full readback. This tool is hidden by tool-visibility control until the
    platform determines those conditions are met.

    Returns:
        dict: On success: {"success": True, "claim_id": <str>}.
        On Firestore write failure: {"success": False, "error": <str>,
        "agent_action": "Apologize that the claim couldn't be lodged due to a
        system issue, then ask for/confirm the best callback number so a
        consultant can follow up directly. End the call once you have it."}
        Cloud Task/Gmail send outcome is never reflected here -- it happens
        after the call has ended (tdd.md §12).
    """
    draft = context.state.get("claim_notification_draft") or {}
    claim_id = str(uuid.uuid4())

    document = {
        "claim_id": claim_id,
        "submitted_at": datetime.datetime.utcnow().isoformat() + "Z",
        "field_status": {},
    }
    for name in _SLOT_NAMES:
        slot = draft.get(name, {})
        document[name] = slot.get("value", "")
        document["field_status"][name] = slot.get("status", "unfilled")

    # -------------------------------------------------------------------
    # STEP 1: Synchronous Firestore write -- the only thing the call waits on.
    # -------------------------------------------------------------------
    try:
        from google.cloud import firestore

        db = firestore.Client(project=_PROJECT_ID, database=_FIRESTORE_DATABASE)
        db.collection(_FIRESTORE_COLLECTION).document(claim_id).set(document)
    except Exception as e:
        return {
            "success": False,
            "error": f"Firestore write failed: {str(e)}",
            "agent_action": (
                "Apologize that the claim couldn't be lodged due to a system "
                "issue right now. Ask for or confirm the best callback "
                "number so a consultant can follow up directly, then end "
                "the call."
            ),
        }

    # -------------------------------------------------------------------
    # STEP 2: Async, fire-and-forget Cloud Task enqueue. A failure here is an
    # infrastructure-level concern (tdd.md §12) -- it does NOT change the
    # tool's return value, since the Firestore record (system of record) is
    # already durable.
    # -------------------------------------------------------------------
    try:
        from google.cloud import tasks_v2

        tasks_client = tasks_v2.CloudTasksClient()
        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": _EMAIL_FUNCTION_URI,
                "headers": {"Content-Type": "application/json"},
                "body": (
                    '{"claim_id": "%s", "collection": "%s", "database": "%s"}'
                    % (claim_id, _FIRESTORE_COLLECTION, _FIRESTORE_DATABASE)
                ).encode("utf-8"),
                "oidc_token": {"service_account_email": _SERVICE_ACCOUNT},
            }
        }
        tasks_client.create_task(parent=_CLOUD_TASKS_QUEUE, task=task)
    except Exception as e:
        # Fire-and-forget: log only. Does not affect the caller-facing
        # outcome -- see module docstring's Error Handling note.
        print(f"submit_claim_notification: Cloud Task enqueue failed (non-blocking, infra concern): {e}")

    return {"success": True, "claim_id": claim_id}
