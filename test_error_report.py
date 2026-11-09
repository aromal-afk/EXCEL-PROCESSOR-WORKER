
from pathlib import Path
from tempfile import TemporaryDirectory

from app.error_report import generate_error_csv


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

    result = generate_error_csv(
        errors,
        csv_path,
    )

    print("CSV generated:", result.exists())
    print("CSV contents:")
    print(result.read_text(encoding="utf-8"))

    empty_result = generate_error_csv(
        [],
        Path(temp_dir) / "empty.csv",
    )

    print(
        "No errors returns None:",
        empty_result is None,
    )
