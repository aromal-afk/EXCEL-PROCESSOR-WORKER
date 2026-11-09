
from app.processor import import_excel_to_firestore

result = import_excel_to_firestore(
    file_path="test_employees.xlsx",
    job_id="day3-test-001",
)

print("\nImport result:")
print(result)
