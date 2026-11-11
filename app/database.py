
import hashlib
import os
from concurrent.futures import (
    FIRST_COMPLETED,
    ThreadPoolExecutor,
    wait,
)

from google.api_core import exceptions, retry
from google.cloud import firestore

from app.config import BATCH_SIZE, WRITE_CONCURRENCY


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

COMMIT_RETRY = retry.Retry(
    predicate=retry.if_exception_type(
        exceptions.Aborted,
        exceptions.DeadlineExceeded,
        exceptions.InternalServerError,
        exceptions.ResourceExhausted,
        exceptions.ServiceUnavailable,
    ),
    initial=0.5,
    maximum=30.0,
    multiplier=2.0,
    deadline=120.0,
)


def employee_document_id(job_id, row_number):
    """
    Deterministic document ID spread across the key space.

    Sequential IDs like "{job_id}_{row}" land on one key
    range and trigger Firestore hotspotting under parallel
    writes; SHA-1 keeps retries idempotent while spreading
    load evenly.
    """
    key = f"{job_id}:{row_number}".encode("utf-8")

    return hashlib.sha1(key).hexdigest()


def _commit_batch(batch, count):
    batch.commit(retry=COMMIT_RETRY)

    return count


def save_records_in_batches(
    job_id,
    records,
    batch_size=BATCH_SIZE,
    write_concurrency=WRITE_CONCURRENCY,
    before_commit=None,
):
    """
    Save employee records in batches, keeping up to
    write_concurrency commits in flight while parsing
    continues on the calling thread.

    before_commit is an optional callback that verifies
    processing ownership before a batch is submitted.
    """

    if not 1 <= batch_size <= 500:
        raise ValueError(
            "batch_size must be between 1 and 500"
        )

    if not 1 <= write_concurrency <= 16:
        raise ValueError(
            "write_concurrency must be between 1 and 16"
        )

    employees = db.collection("employees")
    batch = db.batch()
    pending = 0
    total_saved = 0
    in_flight = set()

    def drain_completed(block_until_below):
        nonlocal total_saved

        while len(in_flight) >= block_until_below:
            done, _ = wait(
                in_flight,
                return_when=FIRST_COMPLETED,
            )

            for future in done:
                in_flight.remove(future)
                total_saved += future.result()

    with ThreadPoolExecutor(
        max_workers=write_concurrency
    ) as pool:
        try:
            for row_number, record in records:
                document_ref = employees.document(
                    employee_document_id(job_id, row_number)
                )

                batch.set(
                    document_ref,
                    {
                        **record,
                        "job_id": job_id,
                        "source_row": row_number,
                    },
                )

                pending += 1

                if pending >= batch_size:
                    drain_completed(write_concurrency)

                    if before_commit:
                        before_commit()

                    in_flight.add(
                        pool.submit(
                            _commit_batch, batch, pending
                        )
                    )

                    batch = db.batch()
                    pending = 0

            if pending:
                drain_completed(write_concurrency)

                if before_commit:
                    before_commit()

                in_flight.add(
                    pool.submit(
                        _commit_batch, batch, pending
                    )
                )

            drain_completed(1)

        except Exception:
            for future in in_flight:
                future.cancel()
            raise

    return total_saved
