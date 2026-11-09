
import csv
from pathlib import Path
import os
from google.cloud import storage
def generate_error_csv(errors, output_path):
    """
    Generate a CSV report for invalid Excel rows.
    """

    if not errors:
        return None

    output_path = Path(output_path)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        output_path,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["row_number", "error"],
        )

        writer.writeheader()

        for error in errors:
            writer.writerow({
                "row_number": error["row_number"],
                "error": error["error"],
            })

    return output_path


BUCKET_NAME = os.getenv(
    "BUCKET_NAME",
    "bulk-excel-processor",
)


def upload_error_report(job_id, csv_path):
    """
    Upload an error CSV to private GCS storage.

    Returns the GCS object name.
    """

    if not csv_path:
        return None

    object_name = f"reports/{job_id}/errors.csv"

    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(object_name)

    blob.upload_from_filename(
        str(csv_path),
        content_type="text/csv",
    )

    return object_name
