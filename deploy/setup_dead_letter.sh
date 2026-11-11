#!/usr/bin/env bash
# Add a dead-letter topic to the existing push subscription so messages that
# keep failing are parked instead of retried forever.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-bulk-excel-processor}"
SUBSCRIPTION="${SUBSCRIPTION:-excel-worker-push-sub}"
DLQ_TOPIC="${DLQ_TOPIC:-excel-processing-jobs-dlq}"
# Larger than MAX_ATTEMPTS: "worker busy" (429/503) redeliveries also count.
MAX_DELIVERY_ATTEMPTS="${MAX_DELIVERY_ATTEMPTS:-10}"

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
PUBSUB_AGENT="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"

gcloud pubsub topics describe "$DLQ_TOPIC" --project "$PROJECT_ID" >/dev/null 2>&1 \
  || gcloud pubsub topics create "$DLQ_TOPIC" --project "$PROJECT_ID"

gcloud pubsub subscriptions describe "${DLQ_TOPIC}-sub" --project "$PROJECT_ID" >/dev/null 2>&1 \
  || gcloud pubsub subscriptions create "${DLQ_TOPIC}-sub" --topic "$DLQ_TOPIC" --project "$PROJECT_ID"

# Pub/Sub's service agent forwards dead letters and acks the original.
gcloud pubsub topics add-iam-policy-binding "$DLQ_TOPIC" \
  --project "$PROJECT_ID" --member "$PUBSUB_AGENT" --role roles/pubsub.publisher
gcloud pubsub subscriptions add-iam-policy-binding "$SUBSCRIPTION" \
  --project "$PROJECT_ID" --member "$PUBSUB_AGENT" --role roles/pubsub.subscriber

gcloud pubsub subscriptions update "$SUBSCRIPTION" \
  --project "$PROJECT_ID" \
  --dead-letter-topic "$DLQ_TOPIC" \
  --max-delivery-attempts "$MAX_DELIVERY_ATTEMPTS" \
  --min-retry-delay 10s \
  --max-retry-delay 600s
