"""
Local benchmark for the Excel parsing/validation stage.

Generates Workers-template files of increasing size, then measures
throughput and peak memory of:

  * streaming  - app.processor.process_excel (openpyxl read_only, row generator)
  * full-load  - openpyxl normal mode, whole workbook materialised in memory

No Firestore writes are performed, so this isolates parsing cost.

Usage:
    python -m benchmarks.benchmark_processing --rows 10000 50000 100000
"""

import argparse
import gc
import random
import time
import tracemalloc
from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl import Workbook, load_workbook

from app.processor import EXPECTED_HEADERS, process_excel


def generate_workbook(path, rows, invalid_ratio=0.05, seed=42):
    """Write a Workers-template file using constant memory."""
    rng = random.Random(seed)
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Template")
    sheet.append(EXPECTED_HEADERS)

    for index in range(rows):
        invalid = rng.random() < invalid_ratio
        sheet.append([
            "" if invalid else f"Employee {index}",
            "Generated for benchmarking",
            f"EMP{index:07d}",
            "Technician",
            rng.choice(["Contractor", "Company Employee"]),
            rng.choice(["Maintenance", "Operations", "Safety"]),
            rng.choice(["System user", "Operator", "Worker"]),
            "not-an-email" if invalid else f"employee{index}@example.com",
            "Model X",
            "Tablet",
            "Field",
            rng.choice(["Day", "Night"]),
            "",
        ])

    workbook.save(path)


def measure(func):
    """Return (result, seconds, peak_bytes).

    tracemalloc slows Python down several times, so timing and
    memory are measured in two separate runs.
    """
    gc.collect()
    started = time.perf_counter()
    result = func()
    elapsed = time.perf_counter() - started

    gc.collect()
    tracemalloc.start()
    func()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, elapsed, peak


def run_streaming(path):
    valid = invalid = 0
    for _, _, error in process_excel(path):
        if error:
            invalid += 1
        else:
            valid += 1
    return valid, invalid


def run_full_load(path):
    workbook = load_workbook(path, data_only=True)
    rows = list(workbook.worksheets[0].iter_rows(values_only=True))
    workbook.close()
    return len(rows) - 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rows", type=int, nargs="+",
        default=[1_000, 10_000, 50_000, 100_000],
    )
    parser.add_argument(
        "--skip-full-load", action="store_true",
        help="Skip the in-memory comparison (slow for huge files).",
    )
    args = parser.parse_args()

    header = (
        f"{'rows':>9} {'file MB':>8} | {'stream s':>9} {'rows/s':>9} "
        f"{'peak MB':>8} | {'full s':>8} {'peak MB':>8}"
    )
    print(header)
    print("-" * len(header))

    with TemporaryDirectory() as temp_dir:
        for rows in args.rows:
            path = Path(temp_dir) / f"bench_{rows}.xlsx"
            generate_workbook(path, rows)
            size_mb = path.stat().st_size / 1_048_576

            (valid, invalid), stream_s, stream_peak = measure(
                lambda: run_streaming(path)
            )
            assert valid + invalid == rows, (valid, invalid, rows)

            if args.skip_full_load:
                full = "        -        -"
            else:
                _, full_s, full_peak = measure(lambda: run_full_load(path))
                full = f"{full_s:>8.2f} {full_peak / 1_048_576:>8.1f}"

            print(
                f"{rows:>9,} {size_mb:>8.2f} | {stream_s:>9.2f} "
                f"{rows / stream_s:>9,.0f} {stream_peak / 1_048_576:>8.1f} | "
                f"{full}"
            )

            path.unlink()


if __name__ == "__main__":
    main()
