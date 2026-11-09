
import os

from google.cloud import firestore


PROJECT_ID = os.getenv(
    "GCP_PROJECT_ID",
    "bulk-excel-processor"
)

DATABASE_ID = os.getenv(
    "FIRESTORE_DATABASE",
    "(default)"
)

db = firestore.Client(
    project=PROJECT_ID,
    database=DATABASE_ID,
)



def save_records_in_batches(
    job_id,
    records,
    batch_size=200,
    before_commit=None,
):
    """
    Save employee records in batches.

    before_commit is an optional callback that
    verifies processing ownership before writes.
    """

    if not 1 <= batch_size <= 500:
        raise ValueError(
            "batch_size must be between 1 and 500"
        )

    batch = db.batch()
    pending = 0
    total_saved = 0

    for row_number, record in records:
        document_id = f"{job_id}_{row_number}"

        document_ref = (
            db.collection("employees")
            .document(document_id)
        )

        batch.set(
            document_ref,
            {
                **record,
                "job_id": job_id,
                "source_row": row_number,
            }
        )

        pending += 1

        if pending >= batch_size:
            if before_commit:
                before_commit()

            batch.commit()
            total_saved += pending

            batch = db.batch()
            pending = 0

    if pending:
        if before_commit:
            before_commit()

        batch.commit()
        total_saved += pending

    return total_saved
