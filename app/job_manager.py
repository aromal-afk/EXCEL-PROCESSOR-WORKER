\
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from google.cloud import firestore
from app.database import db


LEASE_DURATION = timedelta(minutes=10)
MAX_ATTEMPTS = 3

COMPLETED_STATUSES = (
    "Completed",
    "CompletedWithErrors",
)


# --------------------------------------------------
# Claim a job for processing
# --------------------------------------------------

@firestore.transactional
def _claim_job(transaction, job_ref, attempt_id):
    snapshot = job_ref.get(transaction=transaction)

    if not snapshot.exists:
        return {
            "claimed": False,
            "reason": "not_found",
        }

    job = snapshot.to_dict()
    status = job.get("status")
    attempt_count = job.get("attempt_count", 0)

    # Already completed jobs cannot be processed again.
    if status in COMPLETED_STATUSES:
        return {
            "claimed": False,
            "reason": "completed",
        }

    # Permanently failed jobs cannot be retried.
    if status == "Failed":
        return {
            "claimed": False,
            "reason": "failed",
        }

    now = datetime.now(timezone.utc)
    lease_expires_at = job.get("lease_expires_at")

    # Check whether another worker owns the job.
    if status == "Processing":
        if lease_expires_at and lease_expires_at > now:
            return {
                "claimed": False,
                "reason": "active",
            }

    elif status not in (
        "Queued",
        "Queueing",
        "RetryPending",
    ):
        return {
            "claimed": False,
            "reason": "invalid_status",
        }

    # Stop processing after maximum attempts.
    if attempt_count >= MAX_ATTEMPTS:
        transaction.update(
            job_ref,
            {
                "status": "Failed",
                "updated_at": now,
                "lease_expires_at": None,
            },
        )

        return {
            "claimed": False,
            "reason": "max_attempts",
        }

    # Atomically assign processing ownership.
    transaction.update(
        job_ref,
        {
            "status": "Processing",
            "attempt_id": attempt_id,
            "attempt_count": attempt_count + 1,
            "lease_expires_at": now + LEASE_DURATION,
            "started_at": now,
            "updated_at": now,
        },
    )

    return {
        "claimed": True,
        "attempt_id": attempt_id,
        "job": job,
    }


def claim_job(job_id):
    """
    Atomically claim a job for processing.
    """
    job_ref = db.collection("jobs").document(job_id)
    attempt_id = str(uuid4())

    return _claim_job(
        db.transaction(),
        job_ref,
        attempt_id,
    )


# --------------------------------------------------
# Mark a successfully processed job as completed
# --------------------------------------------------

@firestore.transactional
def _finish_job(transaction, job_ref, attempt_id, result):
    snapshot = job_ref.get(transaction=transaction)

    if not snapshot.exists:
        return False

    job = snapshot.to_dict()

    # Only the current attempt can finish.
    if (
        job.get("status") != "Processing"
        or job.get("attempt_id") != attempt_id
    ):
        return False

    now = datetime.now(timezone.utc)

    final_status = (
        "CompletedWithErrors"
        if result["invalid_rows"] > 0
        else "Completed"
    )

    # Save final processing results.
    transaction.update(
        job_ref,
        {
            "status": final_status,
            "valid_rows": result["valid_rows"],
            "invalid_rows": result["invalid_rows"],
            "saved_records": result["saved_records"],

            # Day 4: Store error report GCS path.
            "error_report_object_name": result.get(
                "error_report_object_name"
            ),

            "completed_at": now,
            "updated_at": now,
            "lease_expires_at": None,
        },
    )

    return True


def finish_job(job_id, attempt_id, result):
    """
    Mark a job as completed if the current
    worker still owns the processing attempt.
    """
    job_ref = db.collection("jobs").document(job_id)

    return _finish_job(
        db.transaction(),
        job_ref,
        attempt_id,
        result,
    )


# --------------------------------------------------
# Record processing failures and manage retries
# --------------------------------------------------

@firestore.transactional
def _record_job_failure(
    transaction,
    job_ref,
    attempt_id,
    error_message,
):
    snapshot = job_ref.get(transaction=transaction)

    if not snapshot.exists:
        return False

    job = snapshot.to_dict()

    # Prevent outdated workers from modifying
    # the current job's status.
    if (
        job.get("status") != "Processing"
        or job.get("attempt_id") != attempt_id
    ):
        return False

    now = datetime.now(timezone.utc)
    attempt_count = job.get("attempt_count", 1)

    # Determine whether another retry is allowed.
    next_status = (
        "Failed"
        if attempt_count >= MAX_ATTEMPTS
        else "RetryPending"
    )

    transaction.update(
        job_ref,
        {
            "status": next_status,
            "last_error": str(error_message)[:1000],
            "last_failed_at": now,
            "updated_at": now,
            "lease_expires_at": None,
        },
    )

    return True


def record_job_failure(job_id, attempt_id, error_message):
    """
    Record a failed processing attempt.

    After MAX_ATTEMPTS failures:
        status = Failed

    Otherwise:
        status = RetryPending
    """
    job_ref = db.collection("jobs").document(job_id)

    return _record_job_failure(
        db.transaction(),
        job_ref,
        attempt_id,
        error_message,
    )


# --------------------------------------------------
# Renew processing lease
# --------------------------------------------------

@firestore.transactional
def _renew_job_lease(transaction, job_ref, attempt_id):
    snapshot = job_ref.get(transaction=transaction)

    if not snapshot.exists:
        return False

    job = snapshot.to_dict()
    now = datetime.now(timezone.utc)

    if (
        job.get("status") != "Processing"
        or job.get("attempt_id") != attempt_id
    ):
        return False

    lease_expires_at = job.get("lease_expires_at")

    # An expired lease cannot be renewed.
    if (
        lease_expires_at is None
        or lease_expires_at <= now
    ):
        return False

    transaction.update(
        job_ref,
        {
            "lease_expires_at": now + LEASE_DURATION,
            "updated_at": now,
        },
    )

    return True


def renew_job_lease(job_id, attempt_id):
    """
    Extend a processing lease if the attempt
    still owns the job and its lease is valid.
    """
    job_ref = db.collection("jobs").document(job_id)

    return _renew_job_lease(
        db.transaction(),
        job_ref,
        attempt_id,
    )
