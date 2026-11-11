#!/usr/bin/env bash
# Build and deploy the worker to Cloud Run.
#
# Parallelism = MAX_CONCURRENT_JOBS (files per container) x MAX_INSTANCES.
# Override any variable inline, e.g.:
#   MAX_INSTANCES=10 MAX_CONCURRENT_JOBS=2 BATCH_SIZE=400 ./deploy/deploy_worker.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-bulk-excel-processor}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-excel-worker}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-excel-worker@${PROJECT_ID}.iam.gserviceaccount.com}"
BUCKET_NAME="${BUCKET_NAME:-bulk-excel-processor}"
FIRESTORE_DATABASE="${FIRESTORE_DATABASE:-(default)}"

MAX_CONCURRENT_JOBS="${MAX_CONCURRENT_JOBS:-1}"
MAX_INSTANCES="${MAX_INSTANCES:-5}"
BATCH_SIZE="${BATCH_SIZE:-500}"
WRITE_CONCURRENCY="${WRITE_CONCURRENCY:-8}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"
LEASE_SECONDS="${LEASE_SECONDS:-600}"
LEASE_RENEW_SECONDS="${LEASE_RENEW_SECONDS:-60}"
MEMORY="${MEMORY:-1Gi}"
CPU="${CPU:-1}"
# Must cover the 600s Pub/Sub ack deadline for large files.
TIMEOUT="${TIMEOUT:-900}"

cd "$(dirname "$0")/.."

gcloud run deploy "$SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --source . \
  --service-account "$SERVICE_ACCOUNT" \
  --no-allow-unauthenticated \
  --concurrency "$MAX_CONCURRENT_JOBS" \
  --max-instances "$MAX_INSTANCES" \
  --memory "$MEMORY" \
  --cpu "$CPU" \
  --timeout "$TIMEOUT" \
  --set-env-vars "^|^GCP_PROJECT_ID=${PROJECT_ID}|BUCKET_NAME=${BUCKET_NAME}|FIRESTORE_DATABASE=${FIRESTORE_DATABASE}|MAX_CONCURRENT_JOBS=${MAX_CONCURRENT_JOBS}|BATCH_SIZE=${BATCH_SIZE}|WRITE_CONCURRENCY=${WRITE_CONCURRENCY}|MAX_ATTEMPTS=${MAX_ATTEMPTS}|LEASE_SECONDS=${LEASE_SECONDS}|LEASE_RENEW_SECONDS=${LEASE_RENEW_SECONDS}"
