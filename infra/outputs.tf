output "audio_eval_gcs_bucket" {
  description = "gs:// URL for gecx-config.json's gcs_bucket field."
  value       = "gs://${google_storage_bucket.audio_evals.name}"
}

output "firestore_database_id" {
  description = "Named Firestore database holding claim_notifications. Pass this to the submit_claim_notification tool's config."
  value       = google_firestore_database.claims.name
}

output "service_account_email" {
  description = "Service account used by the agent's tools and the async email Cloud Function. Grant this the domain-wide-delegation Gmail-send scope manually in Workspace Admin — see README.md."
  value       = google_service_account.agent.email
}

output "cloud_tasks_queue" {
  description = "Fully-qualified Cloud Tasks queue name to enqueue against from submit_claim_notification."
  value       = google_cloud_tasks_queue.claim_email_dispatch.id
}

output "send_claim_email_function_uri" {
  description = "HTTPS URI the Cloud Task should target (with an OIDC token for service_account_email)."
  value       = google_cloudfunctions2_function.send_claim_email.url
}
