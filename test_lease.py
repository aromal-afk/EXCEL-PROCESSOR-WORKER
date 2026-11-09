
from uuid import uuid4

from app.database import db
from app.job_manager import (
    claim_job,
    renew_job_lease,
)


job_id = f"lease-test-{uuid4().hex[:8]}"
job_ref = db.collection("jobs").document(job_id)

job_ref.set({
    "status": "Queued",
    "object_name": "uploads/test/input.xlsx",
})

claim = claim_job(job_id)

print("Job claimed:", claim["claimed"])

before = job_ref.get().get("lease_expires_at")

renewed = renew_job_lease(
    job_id,
    claim["attempt_id"],
)

after = job_ref.get().get("lease_expires_at")

print("Lease renewed:", renewed)
print("Expiration extended:", after > before)

invalid_renewal = renew_job_lease(
    job_id,
    "incorrect-attempt-id",
)

print("Wrong attempt rejected:", not invalid_renewal)
