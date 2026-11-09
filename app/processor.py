
import re
from pathlib import Path

from openpyxl import load_workbook

from app.database import save_records_in_batches


# Exact column order from the supplied Excel template.
EXPECTED_HEADERS = [
    "Name",
    "Description",
    "EmployeeID",
    "Title",
    "Employee Type(Contractor or Company Employee)",
    "Department",
    "Profile(System user, Operator, Worker)",
    "e-mail",
    "Equipment Models",
    "Device Types",
    "Role",
    "Shift",
    "Photo",
]

# Internal field names used in Firestore.
FIELD_NAMES = [
    "name",
    "description",
    "employee_id",
    "title",
    "employee_type",
    "department",
    "profile",
    "email",
    "equipment_models",
    "device_types",
    "role",
    "shift",
    "photo",
]

EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)

EMPLOYEE_TYPES = {
    "contractor": "Contractor",
    "company employee": "Company Employee",
}

PROFILES = {
    "system user": "System user",
    "operator": "Operator",
    "worker": "Worker",
}


def normalize_header(value):
    """Normalize whitespace and case in headers."""
    if value is None:
        return ""

    return " ".join(str(value).split()).casefold()


def clean_value(value):
    """Convert Excel cell values to strings."""
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    return str(value).strip()


def validate_row(values):
    """
    Validate one row from the Workers template.

    Required fields:
        Name, EmployeeID, Title, e-mail, Role

    Returns:
        (record, None) if valid
        (None, error_message) if invalid
    """

    record = {
        field: clean_value(value)
        for field, value in zip(FIELD_NAMES, values)
    }

    errors = []

    # Validate required fields.
    required_fields = {
        "name": "Name",
        "employee_id": "EmployeeID",
        "title": "Title",
        "email": "e-mail",
        "role": "Role",
    }

    for field, label in required_fields.items():
        if not record[field]:
            errors.append(f"{label} is required")

    # Validate email format.
    email = record["email"].lower()

    if email and not EMAIL_PATTERN.fullmatch(email):
        errors.append("Invalid email address")

    record["email"] = email

    # Validate employee type when provided.
    employee_type = record["employee_type"]

    if employee_type:
        normalized_type = employee_type.casefold()

        if normalized_type not in EMPLOYEE_TYPES:
            errors.append(
                "Employee Type must be Contractor "
                "or Company Employee"
            )
        else:
            record["employee_type"] = (
                EMPLOYEE_TYPES[normalized_type]
            )

    # Validate profile when provided.
    profile = record["profile"]

    if profile:
        normalized_profile = profile.casefold()

        if normalized_profile not in PROFILES:
            errors.append(
                "Profile must be System user, "
                "Operator, or Worker"
            )
        else:
            record["profile"] = (
                PROFILES[normalized_profile]
            )

    if errors:
        return None, "; ".join(errors)

    return record, None

def process_excel(file_path):
    """
    Read the first worksheet incrementally.

    Yields:
        (row_number, record, error)
    """

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Excel file not found: {file_path}"
        )

    workbook = load_workbook(
        filename=file_path,
        read_only=True,
        data_only=True,
    )

    try:
        if not workbook.worksheets:
            raise ValueError(
                "Excel workbook has no worksheets"
            )

        sheet = workbook.worksheets[0]
        rows = sheet.iter_rows(values_only=True)

        headers = next(rows, None)

        if headers is None:
            raise ValueError("Excel file is empty")

        actual_headers = [
            normalize_header(header)
            for header in headers
        ]

        expected_headers = [
            normalize_header(header)
            for header in EXPECTED_HEADERS
        ]

        if actual_headers != expected_headers:
            raise ValueError(
                "Invalid Excel template. "
                f"Expected columns: {EXPECTED_HEADERS}"
            )

        for row_number, row in enumerate(
            rows,
            start=2,
        ):
            # Ignore completely empty rows.
            if not any(
                value is not None
                and clean_value(value) != ""
                for value in row
            ):
                continue

            # Ensure the expected number of cells.
            values = list(row[:len(FIELD_NAMES)])

            if len(values) < len(FIELD_NAMES):
                values.extend(
                    [None] * (
                        len(FIELD_NAMES) - len(values)
                    )
                )

            record, error = validate_row(values)

            yield row_number, record, error

    finally:
        workbook.close()


def import_excel_to_firestore(
    file_path,
    job_id,
    before_commit=None,
):
    """
    Validate Excel rows and save valid records
    to Firestore in batches.

    Invalid rows are collected for the
    Day 4 CSV error-report functionality.
    """

    invalid_rows = []
    valid_count = 0

    def valid_records():
        nonlocal valid_count

        for row_number, record, error in process_excel(
            file_path
        ):
            if error:
                invalid_rows.append({
                    "row_number": row_number,
                    "error": error,
                })
            else:
                valid_count += 1

                yield row_number, record

    saved_count = save_records_in_batches(
        job_id=job_id,
        records=valid_records(),
        batch_size=200,
        before_commit=before_commit,
    )

    return {
        "job_id": job_id,
        "valid_rows": valid_count,
        "invalid_rows": len(invalid_rows),
        "saved_records": saved_count,
        "errors": invalid_rows,
    }
