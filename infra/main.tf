locals {
  audio_eval_bucket_name      = coalesce(var.audio_eval_bucket_name, "${var.project_id}-${var.app_name}-audio-evals")
  function_source_bucket_name = "${var.project_id}-${var.app_name}-fn-source"
  firestore_database_id       = "${var.app_name}-fnol"
  service_account_id          = "${var.app_name}-agent"
  task_queue_id               = "claim-email-dispatch"
  function_name               = "send-claim-email"
  compute_default_sa          = "${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

data "google_project" "current" {
  project_id = var.project_id
}

# Some orgs set iam.automaticIamGrantsForDefaultServiceAccounts to DENY,
# which skips the usual automatic roles/editor grant to the Compute Engine
# default service account. Cloud Functions Gen2 builds run as that SA
# unless build_config.service_account is overridden, so without these
# grants the build fails at the source-fetch step with a permission error.
resource "google_project_iam_member" "compute_sa_build_roles" {
  for_each = toset([
    "roles/cloudbuild.builds.builder",
    "roles/storage.objectViewer",
    "roles/artifactregistry.writer",
    "roles/logging.logWriter",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${local.compute_default_sa}"

  depends_on = [google_project_service.required]
}

# --- APIs required by this stack ---
resource "google_project_service" "required" {
  for_each = toset([
    "firestore.googleapis.com",
    "cloudtasks.googleapis.com",
    "cloudfunctions.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "gmail.googleapis.com",
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# --- GCS bucket: CES audio eval recording artifacts ---
resource "google_storage_bucket" "audio_evals" {
  name                        = local.audio_eval_bucket_name
  project                     = var.project_id
  location                    = upper(var.region)
  uniform_bucket_level_access = true
  force_destroy               = false

  depends_on = [google_project_service.required]
}

# --- Firestore: durable claim-notification record store ---
# Named database (not the project's default) so this stack never collides
# with any other Firestore usage in the same project.
resource "google_firestore_database" "claims" {
  project     = var.project_id
  name        = local.firestore_database_id
  location_id = var.firestore_location
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.required]
}

# --- Service account used by the CES agent's tools AND the async email Cloud Function ---
resource "google_service_account" "agent" {
  project      = var.project_id
  account_id   = local.service_account_id
  display_name = "${var.app_name} FNOL agent (Firestore write + Gmail dispatch)"
}

resource "google_project_iam_member" "agent_firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_project_iam_member" "agent_task_enqueuer" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.agent.email}"
}

# --- Cloud Tasks queue: decouples the live call from the Gmail send ---
resource "google_cloud_tasks_queue" "claim_email_dispatch" {
  project  = var.project_id
  name     = local.task_queue_id
  location = var.region

  retry_config {
    max_attempts = 5
  }

  depends_on = [google_project_service.required]
}

# --- Cloud Function source (2nd gen, HTTP-triggered by Cloud Tasks) ---
data "archive_file" "send_claim_email_source" {
  type        = "zip"
  source_dir  = "${path.module}/functions/send_claim_email"
  output_path = "${path.module}/.build/send_claim_email.zip"
}

resource "google_storage_bucket" "function_source" {
  name                        = local.function_source_bucket_name
  project                     = var.project_id
  location                    = upper(var.region)
  uniform_bucket_level_access = true
  force_destroy               = true

  depends_on = [google_project_service.required]
}

resource "google_storage_bucket_object" "send_claim_email_source" {
  name   = "send_claim_email/${data.archive_file.send_claim_email_source.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.send_claim_email_source.output_path
}

resource "google_cloudfunctions2_function" "send_claim_email" {
  project  = var.project_id
  name     = local.function_name
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "send_claim_email"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.send_claim_email_source.name
      }
    }
  }

  service_config {
    max_instance_count    = 5
    available_memory      = "256Mi"
    timeout_seconds       = 60
    service_account_email = google_service_account.agent.email
    environment_variables = {
      FIRESTORE_DATABASE_ID          = google_firestore_database.claims.name
      CLAIM_NOTIFICATION_EMAIL       = var.claim_notification_email
      GMAIL_SEND_AS_USER             = var.gmail_send_as_user
      FUNCTION_SERVICE_ACCOUNT_EMAIL = google_service_account.agent.email
    }
    # HTTP-triggered, invoked only by the Cloud Tasks queue below via an
    # OIDC token minted for this same service account — not public.
    ingress_settings               = "ALLOW_INTERNAL_AND_GCLB"
    all_traffic_on_latest_revision = true
  }

  depends_on = [google_project_service.required, google_project_iam_member.compute_sa_build_roles]
}

# Only the agent service account (the one Cloud Tasks uses to attach an
# OIDC token) may invoke the function.
resource "google_cloud_run_service_iam_member" "invoker" {
  project  = var.project_id
  location = var.region
  service  = google_cloudfunctions2_function.send_claim_email.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.agent.email}"
}
