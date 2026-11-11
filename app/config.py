
import os
from datetime import timedelta


def _int_env(name, default, minimum, maximum):
    value = int(os.getenv(name, default))

    if not minimum <= value <= maximum:
        raise ValueError(
            f"{name} must be between {minimum} and {maximum}"
        )

    return value


# Rows per Firestore WriteBatch (Firestore allows at most 500).
BATCH_SIZE = _int_env("BATCH_SIZE", 500, 1, 500)

# WriteBatch commits kept in flight while rows continue to be parsed.
WRITE_CONCURRENCY = _int_env("WRITE_CONCURRENCY", 8, 1, 16)

# Processing attempts per job before it is marked Failed.
MAX_ATTEMPTS = _int_env("MAX_ATTEMPTS", 3, 1, 20)

# How long a worker owns a job without renewing its lease.
LEASE_SECONDS = _int_env("LEASE_SECONDS", 600, 60, 3600)
LEASE_DURATION = timedelta(seconds=LEASE_SECONDS)

# Minimum interval between lease-renewal transactions during batch writes.
LEASE_RENEW_SECONDS = _int_env(
    "LEASE_RENEW_SECONDS", 60, 10, 300
)

if LEASE_RENEW_SECONDS >= LEASE_SECONDS // 2:
    raise ValueError(
        "LEASE_RENEW_SECONDS must be less than half of LEASE_SECONDS"
    )

# Files processed at the same time inside one container. Should match
# Cloud Run --concurrency; total parallelism is this x --max-instances.
MAX_CONCURRENT_JOBS = _int_env("MAX_CONCURRENT_JOBS", 1, 1, 32)
