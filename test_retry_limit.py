
from uuid import uuid4

from app.database import db
from app.job_manager import claim_job, record_job_failure


job_id = f"retry-test-{uuid4().hex[:8]}"
job_ref = db.collection("jobs").document(job_id)

job_ref.set({
    "status": "Queued",
    "object_name": "uploads/test/input.xlsx",
})

for attempt in range(1, 4):
    claim = claim_job(job_id)

    print(f"Attempt {attempt} claimed:", claim["claimed"])

    record_job_failure(
        job_id,
        claim["attempt_id"],
        f"Simulated failure {attempt}",
    )

    print("Status:", job_ref.get().get("status"))

final_claim = claim_job(job_id)

print("Fourth attempt claimed:", final_claim["claimed"])
print("Reason:", final_claim["reason"])
