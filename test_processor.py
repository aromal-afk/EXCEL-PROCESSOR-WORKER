
from app.processor import process_excel

from openpyxl import Workbook

workbook = Workbook()
sheet = workbook.active

sheet.append(["name", "email", "age"])
sheet.append(["Rahul", "rahul@gmail.com", 25])
sheet.append(["Anjali", "anjali@gmail.com", 28])
sheet.append(["Arun", "invalid-email", 22])
sheet.append(["Meera", "meera@gmail.com", -5])

workbook.save("test_employees.xlsx")

valid_count = 0
invalid_count = 0

for row_number, record, error in process_excel(
    "test_employees.xlsx"
):
    if error:
        invalid_count += 1
        print(f"Row {row_number}: INVALID - {error}")
    else:
        valid_count += 1
        print(f"Row {row_number}: VALID - {record}")

print(f"\nValid rows: {valid_count}")
print(f"Invalid rows: {invalid_count}")
