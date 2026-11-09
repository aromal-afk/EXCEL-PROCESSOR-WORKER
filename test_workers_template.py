
from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl import Workbook

from app.processor import (
    EXPECTED_HEADERS,
    process_excel,
)


with TemporaryDirectory() as temp_dir:
    file_path = Path(temp_dir) / "workers_test.xlsx"

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Template"

    sheet.append(EXPECTED_HEADERS)

    # Valid employee.
    sheet.append([
        "Rahul",
        "Maintenance worker",
        "EMP001",
        "Technician",
        "Company Employee",
        "Maintenance",
        "Worker",
        "rahul@example.com",
        "",
        "",
        "Technician",
        "Morning",
        "",
    ])

    # Invalid email.
    sheet.append([
        "Anjali",
        "",
        "EMP002",
        "",
        "Contractor",
        "",
        "Operator",
        "invalid-email",
        "",
        "",
        "",
        "",
        "",
    ])

    # Invalid profile.
    sheet.append([
        "Meera",
        "",
        "EMP003",
        "",
        "Contractor",
        "",
        "Manager",
        "meera@example.com",
        "",
        "",
        "",
        "",
        "",
    ])

    # Missing EmployeeID.
    sheet.append([
        "Arun",
        "",
        "",
        "",
        "Contractor",
        "",
        "Worker",
        "arun@example.com",
        "",
        "",
        "",
        "",
        "",
    ])

    workbook.save(file_path)

    valid_count = 0
    invalid_count = 0

    for row_number, record, error in process_excel(
        file_path
    ):
        if error:
            invalid_count += 1
            print(f"Row {row_number}: INVALID - {error}")
        else:
            valid_count += 1
            print(
                f"Row {row_number}: VALID - "
                f"{record['employee_id']}"
            )

    print("Valid rows:", valid_count)
    print("Invalid rows:", invalid_count)

    assert valid_count == 1
    assert invalid_count == 3

    print("All tests passed!")
