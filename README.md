# EXCEL-PROCESSOR-WORKER

Background worker for the Bulk Excel Processor. It receives Pub/Sub push
messages, claims the job in Firestore, streams the uploaded `.xlsx` from Cloud
Storage, validates each row, saves valid rows to Firestore in batches and uploads
a CSV report for invalid rows.

Full architecture, design decisions, deployment and performance results live in
the main README:
[EXCEL-PROCESSOR-API/README.md](https://github.com/aromal-afk/EXCEL-PROCESSOR-API#readme).

## How it works

| Module | Responsibility |
|---|---|
| `app/main.py` | `POST /pubsub/push`: decode message, claim, download, process, finish or record failure |
| `app/job_manager.py` | Firestore transactions: claim with `attempt_id` + 10-minute lease, renew lease, finish, record failure (max 3 attempts) |
| `app/processor.py` | Streams the first sheet with `openpyxl` `read_only=True`, checks the template header, validates rows |
| `app/database.py` | Writes valid rows in `WriteBatch`es of 500 with up to `WRITE_CONCURRENCY` commits in flight, using deterministic hashed IDs `sha1("{job_id}:{row}")` |
| `app/error_report.py` | Writes `errors.csv` and uploads it to `reports/{job_id}/errors.csv` |

Response codes drive Pub/Sub's behaviour:

* `200` means the message is acknowledged: the job is done, or was already completed or failed.
* `400` means the payload is malformed.
* `503` means try again later: processing failed and will be retried, or another worker currently holds the lease.

## Configuration

All settings are environment variables (`app/config.py`); invalid values stop the container at startup.

| Variable | Default | Meaning |
|---|---|---|
| `GCP_PROJECT_ID` | `bulk-excel-processor` | Project for Firestore and Cloud Storage |
| `BUCKET_NAME` | `bulk-excel-processor` | Bucket containing `uploads/` and `reports/` |
| `FIRESTORE_DATABASE` | `(default)` | Firestore database. Must match the API's database |
| `MAX_CONCURRENT_JOBS` | `1` | Files processed at once per container. Extra deliveries get a 429 and Pub/Sub retries them later |
| `BATCH_SIZE` | `500` | Rows per Firestore `WriteBatch` (1–500) |
| `WRITE_CONCURRENCY` | `8` | `WriteBatch` commits kept in flight while rows continue to be parsed (1–16) |
| `MAX_ATTEMPTS` | `3` | Processing attempts before a job becomes `Failed` |
| `LEASE_SECONDS` | `600` | How long a job stays owned without a lease renewal |
| `LEASE_RENEW_SECONDS` | `60` | Minimum interval between lease renewals during batch writes (must be `< LEASE_SECONDS / 2`) |

Total parallelism is `MAX_CONCURRENT_JOBS` × Cloud Run `--max-instances`.
`deploy/deploy_worker.sh` keeps Cloud Run `--concurrency` equal to
`MAX_CONCURRENT_JOBS`, so Cloud Run itself routes extra messages to other instances.

### Document IDs and very large files

* Each valid row is saved to `employees` with document ID `sha1("{job_id}:{row}")`
  (plus `job_id` and `source_row` fields). Because the ID is deterministic, retries
  overwrite the same document instead of duplicating rows; hashing spreads keys
  evenly across Firestore so parallel commits don't hotspot a single prefix.
* For files with hundreds of thousands of rows, splitting into several `.xlsx` files
  and uploading them together lets up to `MAX_INSTANCES × MAX_CONCURRENT_JOBS`
  workers process parts in parallel, while keeping each job well within Cloud Run's
  timeout and memory budget. Cross-file `EmployeeID` uniqueness is not enforced.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GCP_PROJECT_ID=<project> BUCKET_NAME=<bucket> FIRESTORE_DATABASE="(default)"
uvicorn app.main:app --reload --port 8001
```

Pub/Sub can't reach `localhost`, so simulate a push:

```bash
DATA=$(echo -n '{"job_id":"<job-id>"}' | base64)
curl -X POST localhost:8001/pubsub/push -H 'Content-Type: application/json' \
     -d "{\"message\":{\"data\":\"$DATA\"}}"
```

## Benchmark

```bash
python -m benchmarks.benchmark_processing --rows 1000 10000 50000 100000
```

Latest results are in [`benchmarks/results/processing_benchmark.txt`](benchmarks/results/processing_benchmark.txt).
At 100,000 rows, streaming peaks at 8.4 MB of memory while a normal workbook
load peaks at 496 MB, at the same speed (about 3,100 rows/s).

## Deploy

The worker runs on Cloud Run as `excel-worker` in `us-central1`. It is private, and
only the `pubsub-worker-invoker` service account (used by the
`excel-worker-push-sub` push subscription, with OIDC tokens) may invoke it.

```bash
./deploy/deploy_worker.sh                                  # defaults: 1 job/container, 5 instances
MAX_INSTANCES=10 MAX_CONCURRENT_JOBS=2 ./deploy/deploy_worker.sh
./deploy/setup_dead_letter.sh                              # one-off: dead-letter topic + retry backoff
```
