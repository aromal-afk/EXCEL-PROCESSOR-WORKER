
from datetime import datetime, timezone
from uuid import uuid4

from app.database import db
from app.job_manager import (
    claim_job,
    record_job_failure,
)


job_id = f"day3-failure-test-{uuid4().hex[:8]}"

job_ref = db.collection("jobs").document(job_id)

job_ref.set({
    "status": "Queued",
    "object_name": "uploads/test/input.xlsx",
    "created_at": datetime.now(timezone.utc),
})

claim = claim_job(job_id)

print("Claimed:", claim["claimed"])

failed = record_job_failure(
    job_id=job_id,
    attempt_id=claim["attempt_id"],
    error_message="Simulated processing failure",
)

print("Failure recorded:", failed)

snapshot = job_ref.get()
print("Status after failure:", snapshot.get("status"))

retry_claim = claim_job(job_id)

print("Retry claimed:", retry_claim["claimed"])
print(
    "New attempt ID:",
    retry_claim["attempt_id"] != claim["attempt_id"],
)
