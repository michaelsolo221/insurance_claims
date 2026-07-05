"""Async, post-call email dispatch for FNOL claim notifications.

Triggered by a Cloud Task enqueued from the CES agent's
`submit_claim_notification` tool, after that tool has already written the
claim durably to Firestore and the phone call has ended. A failure here
never reaches the caller (see tdd.md Round 3/§13) — the Firestore record
is the system of truth; this function is a best-effort human-notification
hand-off on top of it.

Domain-wide delegation is done key-lessly: this function's attached
service account signs its own delegation JWT via the IAM Credentials API
(`signJwt`) instead of requiring a downloaded service-account key file —
see infra/README.md for the one-time Workspace Admin authorization step.
"""

import base64
import json
import os
import time

import functions_framework
import google.auth
import google.auth.transport.requests
import requests
from google.cloud import firestore

FIRESTORE_DATABASE_ID = os.environ["FIRESTORE_DATABASE_ID"]
CLAIM_NOTIFICATION_EMAIL = os.environ["CLAIM_NOTIFICATION_EMAIL"]
GMAIL_SEND_AS_USER = os.environ["GMAIL_SEND_AS_USER"]
FUNCTION_SERVICE_ACCOUNT_EMAIL = os.environ["FUNCTION_SERVICE_ACCOUNT_EMAIL"]
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"

db = firestore.Client(database=FIRESTORE_DATABASE_ID)


def _mint_delegated_access_token(subject: str, scope: str) -> str:
    now = int(time.time())
    claim_set = {
        "iss": FUNCTION_SERVICE_ACCOUNT_EMAIL,
        "scope": scope,
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
        "sub": subject,
    }

    credentials, _ = google.auth.default()
    credentials.refresh(google.auth.transport.requests.Request())

    sign_jwt_resp = requests.post(
        f"https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
        f"{FUNCTION_SERVICE_ACCOUNT_EMAIL}:signJwt",
        headers={"Authorization": f"Bearer {credentials.token}"},
        json={"payload": json.dumps(claim_set)},
        timeout=10,
    )
    sign_jwt_resp.raise_for_status()
    signed_jwt = sign_jwt_resp.json()["signedJwt"]

    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": signed_jwt,
        },
        timeout=10,
    )
    token_resp.raise_for_status()
    return token_resp.json()["access_token"]


def _format_claim_email(claim: dict) -> str:
    lines = [f"New FNOL claim notification (claim_id: {claim.get('claim_id', 'unknown')})", ""]
    for field in (
        "caller_name", "callback_phone", "policy_number", "incident_datetime",
        "incident_location", "incident_description", "injury_flag",
        "hazard_flag", "callback_window",
    ):
        slot = claim.get(field, {})
        value = slot.get("value") if isinstance(slot, dict) else slot
        status = slot.get("status") if isinstance(slot, dict) else None
        display = value if value not in (None, "") else "(not captured)"
        lines.append(f"{field}: {display}" + (f"  [{status}]" if status else ""))
    return "\n".join(lines)


def _build_raw_mime_message(sender: str, to: str, subject: str, body: str) -> str:
    message = f"From: {sender}\r\nTo: {to}\r\nSubject: {subject}\r\n\r\n{body}"
    return base64.urlsafe_b64encode(message.encode("utf-8")).decode("utf-8")


@functions_framework.http
def send_claim_email(request):
    """Expects JSON body: {"claim_id": "<Firestore doc ID in claim_notifications>"}."""
    body = request.get_json(silent=True) or {}
    claim_id = body.get("claim_id")
    if not claim_id:
        return ("missing claim_id", 400)

    doc_ref = db.collection("claim_notifications").document(claim_id)
    snapshot = doc_ref.get()
    if not snapshot.exists:
        return (f"claim {claim_id} not found", 404)

    claim = snapshot.to_dict()
    access_token = _mint_delegated_access_token(subject=GMAIL_SEND_AS_USER, scope=GMAIL_SEND_SCOPE)

    raw_message = _build_raw_mime_message(
        sender=GMAIL_SEND_AS_USER,
        to=CLAIM_NOTIFICATION_EMAIL,
        subject=f"New FNOL claim — {claim_id}",
        body=_format_claim_email(claim),
    )

    gmail_resp = requests.post(
        f"https://gmail.googleapis.com/gmail/v1/users/{GMAIL_SEND_AS_USER}/messages/send",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"raw": raw_message},
        timeout=15,
    )

    if gmail_resp.status_code >= 400:
        doc_ref.update({"email_status": "failed", "email_error": gmail_resp.text})
        return (f"gmail send failed: {gmail_resp.text}", 502)

    doc_ref.update({"email_status": "sent"})
    return ("ok", 200)
