variable "project_id" {
  description = "GCP project ID to provision resources into. No default on purpose — every user of this repo must supply their own."
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Function, Cloud Tasks queue, and the Cloud Function source bucket. This is a compute region (e.g. us-central1), distinct from the CES app's 'us' multi-region setting."
  type        = string
  default     = "us-central1"
}

variable "firestore_location" {
  description = "Firestore location ID. Multi-region 'nam5' by default; use a specific region (e.g. us-central1) if you need Firestore and Cloud Function co-located."
  type        = string
  default     = "nam5"
}

variable "app_name" {
  description = "Short name for this agent, used as a prefix for resource names (bucket, queue, service account, Firestore database)."
  type        = string
  default     = "insurance-claims"
}

variable "audio_eval_bucket_name" {
  description = "GCS bucket name for CES audio eval recording artifacts. Must be globally unique. Defaults to '<project_id>-<app_name>-audio-evals' if left null."
  type        = string
  default     = null
}

variable "claim_notification_email" {
  description = "Mailbox that receives the FNOL claim-notification email, sent via the async Cloud Function."
  type        = string
  default     = "michael@michael-lo.com"
}

variable "gmail_send_as_user" {
  description = "Workspace user the service account impersonates via domain-wide delegation to call the Gmail API (must be in the same Workspace domain as claim_notification_email)."
  type        = string
  default     = "michael@michael-lo.com"
}
