
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from google.cloud import storage

from app.error_report import (
    generate_error_csv,
    upload_error_report,
)


job_id = f"test-{uuid4()}"

errors = [
    {
        "row_number": 4,
        "error": "Invalid email address",
    },
    {
        "row_number": 7,
        "error": "Age must be a number",
    },
]

with TemporaryDirectory() as temp_dir:
    csv_path = Path(temp_dir) / "errors.csv"

    generate_error_csv(errors, csv_path)

    object_name = upload_error_report(
        job_id=job_id,
        csv_path=csv_path,
    )

    print("Uploaded object:", object_name)

    # Verify the file exists in GCS.
    client = storage.Client()

    blob = client.bucket(
        "bulk-excel-processor"
    ).blob(object_name)

    print("Exists in GCS:", blob.exists())

    # Verify its contents.
    print("Downloaded contents:")
    print(blob.download_as_text())
