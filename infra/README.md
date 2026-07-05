# Infrastructure (Terraform)

Provisions everything `submit_claim_notification` needs outside the CES app itself:

| Resource | Purpose |
|---|---|
| GCS bucket (`<project_id>-<app_name>-audio-evals`) | CES `evaluationAudioRecordingConfig` storage — required for any audio eval run |
| Firestore database (named, not default) | Durable claim record — the call-blocking write, source of truth |
| Cloud Tasks queue (`claim-email-dispatch`) | Decouples the live call from the Gmail send |
| Cloud Function (`send-claim-email`, 2nd gen) | Async, post-call: sends the human-facing notification email via Gmail API |
| Service account | Used by both the agent's tools and the Cloud Function |

See `tdd.md` (Round 3 / §12-§13) for why this is split into a synchronous durable write + a decoupled async email, instead of one blocking Gmail-send tool.

## Setup

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # fill in your project_id — this file is gitignored, never commit it
terraform init
terraform plan
terraform apply
```

## One manual step: domain-wide delegation

Terraform cannot grant domain-wide delegation — that authorization lives in Google Workspace Admin, not the GCP project, and there's no API for it. After `terraform apply`:

1. Note the `service_account_email` output.
2. In [Google Workspace Admin Console](https://admin.google.com) → Security → API controls → Domain-wide delegation → **Add new**.
3. Client ID: the service account's numeric OAuth2 client ID (`gcloud iam service-accounts describe <service_account_email> --format='value(oauthClientId)'` — if empty, enable it via `gcloud iam service-accounts keys create` is NOT needed; the client ID appears once the SA has been used for at least one OAuth flow, or check the IAM console's service account details page).
4. OAuth scope: `https://www.googleapis.com/auth/gmail.send`
5. This must be done by a Workspace super admin for the `mcosolutions.com.au` domain (or whichever domain owns the `gmail_send_as_user` mailbox).

The Cloud Function signs its own delegation JWT via the IAM Credentials API (`signJwt`) at request time — no service-account key file is ever downloaded or stored.

## Reproducing this for a different project

Every resource name is derived from `var.project_id` / `var.app_name`, and `project_id` has no default — set your own in `terraform.tfvars` and nothing here needs to change. `claim_notification_email` / `gmail_send_as_user` default to `michael@michael-lo.com`; override those too if you're not deploying this exact agent.
