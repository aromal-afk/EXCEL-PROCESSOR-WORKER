
from datetime import datetime, timezone
from uuid import uuid4

from app.database import db
from app.job_manager import claim_job, finish_job


job_id = f"day3-claim-test-{uuid4().hex[:8]}"

db.collection("jobs").document(job_id).set({
    "status": "Queued",
    "object_name": "uploads/test/input.xlsx",
    "created_at": datetime.now(timezone.utc),
})

first_claim = claim_job(job_id)

print("First claim:", first_claim["claimed"])

second_claim = claim_job(job_id)

print("Second claim:", second_claim["claimed"])
print("Second claim reason:", second_claim["reason"])

result = {
    "valid_rows": 2,
    "invalid_rows": 0,
    "saved_records": 2,
}

completed = finish_job(
    job_id,
    first_claim["attempt_id"],
    result,
)

print("Job completed:", completed)

third_claim = claim_job(job_id)

print("Third claim:", third_claim["claimed"])
print("Third claim reason:", third_claim["reason"])
