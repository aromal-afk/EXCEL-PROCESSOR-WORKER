import base64
import binascii
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.cloud import storage

from app.config import (
    LEASE_RENEW_SECONDS,
    MAX_CONCURRENT_JOBS,
)
from app.job_manager import (
    claim_job,
    finish_job,
    record_job_failure,
    renew_job_lease,
)
from app.processor import import_excel_to_firestore
from app.error_report import upload_error_report


# --------------------------------------------------
# Configuration
# --------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Bulk Excel Processing Worker")

storage_client = storage.Client()

BUCKET_NAME = os.getenv(
    "BUCKET_NAME",
    "bulk-excel-processor",
)

job_slots = threading.BoundedSemaphore(MAX_CONCURRENT_JOBS)


# --------------------------------------------------
# Pub/Sub request models
# --------------------------------------------------

class PubSubMessage(BaseModel):
    data: str


class PubSubEnvelope(BaseModel):
    message: PubSubMessage
    subscription: str | None = None


# --------------------------------------------------
# Health endpoint
# --------------------------------------------------

@app.get("/health")
def health():
    return {"status": "healthy"}


# --------------------------------------------------
# Pub/Sub push endpoint
# --------------------------------------------------

@app.post("/pubsub/push")
def handle_pubsub_push(envelope: PubSubEnvelope):

    # Step 1: Decode Pub/Sub message.
    try:
        decoded = base64.b64decode(
            envelope.message.data,
            validate=True,
        )

        payload = json.loads(decoded)
        job_id = payload["job_id"]

        if not isinstance(job_id, str) or not job_id:
            raise ValueError("Invalid job_id")

    except (
        ValueError,
        KeyError,
        TypeError,
        binascii.Error,
        UnicodeDecodeError,
    ) as exc:
        logger.warning(
            "Invalid Pub/Sub payload: %s",
            exc,
        )

        raise HTTPException(
            status_code=400,
            detail="Invalid Pub/Sub message",
        ) from exc

    # A non-2xx response makes Pub/Sub redeliver with backoff,
    # so an overloaded instance never queues work in memory.
    if not job_slots.acquire(blocking=False):
        logger.info(
            "All %d job slots busy; deferring job %s",
            MAX_CONCURRENT_JOBS,
            job_id,
        )
        raise HTTPException(
            status_code=429,
            detail="Worker at capacity; retry later",
        )

    try:
        return _process_job(job_id)
    finally:
        job_slots.release()


def _process_job(job_id):
    # Step 2: Claim processing ownership.
    try:
        claim = claim_job(job_id)
    except Exception as exc:
        logger.exception(
            "Failed to claim job %s",
            job_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to claim job",
        ) from exc

    if not claim["claimed"]:
        reason = claim["reason"]

        # Terminal or nonexistent jobs do not need another
        # retry; acknowledging stops endless redelivery.
        if reason in (
            "completed",
            "failed",
            "max_attempts",
            "not_found",
        ):
            return {
                "status": "already_finished",
                "job_id": job_id,
                "reason": reason,
            }

        # Active jobs or other nonterminal states
        # require retry/recovery handling.
        raise HTTPException(
            status_code=503,
            detail=f"Job not claimed: {reason}",
        )

    attempt_id = claim["attempt_id"]
    job = claim["job"]

    # Step 3: Define lease verification callback.
    # During batch writes, renew at most every
    # LEASE_RENEW_SECONDS instead of on every batch.
    last_renewed = time.monotonic()

    def verify_and_renew(force=False):
        nonlocal last_renewed
        now = time.monotonic()

        if not force and now - last_renewed < LEASE_RENEW_SECONDS:
            return

        renewed = renew_job_lease(
            job_id=job_id,
            attempt_id=attempt_id,
        )

        if not renewed:
            raise RuntimeError(
                "Processing lease lost or expired"
            )

        last_renewed = time.monotonic()

    # Step 4: Download and process Excel.
    try:
        object_name = job.get("object_name")

        if not object_name:
            raise ValueError(
                "Job has no object_name"
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            local_path = Path(temp_dir) / "input.xlsx"

            blob = storage_client.bucket(
                BUCKET_NAME
            ).blob(object_name)

            logger.info(
                "Downloading %s for job %s",
                object_name,
                job_id,
            )

            blob.download_to_filename(
                str(local_path)
            )

            # Verify ownership after downloading.
            verify_and_renew(force=True)

            result = import_excel_to_firestore(
                file_path=local_path,
                job_id=job_id,
                before_commit=verify_and_renew,
                error_report_path=Path(temp_dir) / "errors.csv",
            )

            # Upload the error report written during processing.
            error_report_object_name = None
            csv_path = result.pop("error_report_path")

            if csv_path:
                verify_and_renew(force=True)

                error_report_object_name = upload_error_report(
                    job_id=job_id,
                    csv_path=csv_path,
                )

                verify_and_renew(force=True)

            result["error_report_object_name"] = (
                error_report_object_name
            )

        # Step 5: Mark processing complete only after report upload.
        completed = finish_job(
            job_id=job_id,
            attempt_id=attempt_id,
            result=result,
        )

        if not completed:
            raise RuntimeError(
                "Job ownership changed before completion"
            )

        logger.info(
            "Job %s completed: %s",
            job_id,
            result,
        )

        return {
            "status": "completed",
            "job_id": job_id,
            "result": result,
        }

    # Step 6: Record processing failures.
    except Exception as exc:
        logger.exception(
            "Processing failed for job %s",
            job_id,
        )

        try:
            recorded = record_job_failure(
                job_id=job_id,
                attempt_id=attempt_id,
                error_message=str(exc),
            )

            if not recorded:
                logger.warning(
                    "Could not record failure for job %s; "
                    "processing ownership may have changed",
                    job_id,
                )

        except Exception:
            logger.exception(
                "Failed to update Firestore failure "
                "status for job %s",
                job_id,
            )

        # Pub/Sub retries on non-2xx responses.
        # Once the job is terminally Failed, a
        # subsequent delivery will be acknowledged.
        raise HTTPException(
            status_code=503,
            detail="Processing failed; retry requested",
        ) from exc