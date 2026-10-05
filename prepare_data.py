"""Download and tidy the public six-drug Liver-Chip response supplement."""

from pathlib import Path
from urllib.request import urlretrieve
import csv
import math
import openpyxl

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
SOURCE_ROOT = (
    "https://media.springernature.com/original/springer-static/esm/"
    "art%3A10.1038%2Fs43856-022-00209-1/MediaObjects/"
)


def prepare_data():
    for number in [1, 8]:
        path = RAW / f"supplementary_data_{number}.xlsx"
        if not path.exists():
            url = SOURCE_ROOT + f"43856_2022_209_MOESM{number}_ESM.xlsx"
            urlretrieve(url, path)

    workbook = openpyxl.load_workbook(RAW / "supplementary_data_8.xlsx", data_only=True)
    endpoint_names = {
        "ALBUMIN": "albumin_percent",
        "ALT": "alt_source_units",
        "Morphology": "morphology_score",
    }
    expected_headers = {
        "ALBUMIN": "Normalized_Albumin_Levels",
        "ALT": "ALT_levels",
        "Morphology": "Score",
    }
    records = []
    for sheet in workbook:
        headers = list(next(sheet.values))
        expected = ["Compound_Name", "Concentration_Day3", expected_headers[sheet.title]]
        if headers != expected:
            raise ValueError(f"Source schema changed in {sheet.title}: {headers}")
        for source_row, values in enumerate(sheet.values, start=1):
            if source_row == 1:
                continue
            compound, dose, value = values
            missing = value is None or str(value).strip().lower() in ["na", "nan"]
            if not missing:
                value = float(value)
                missing = not math.isfinite(value)
            records.append({
                "data_origin": "published_real",
                "source_record_id": f"ewart2022_supp8_{sheet.title}_C{source_row}",
                "compound": compound,
                "day": 3,
                "dose_cmax_multiple": float(dose),
                "endpoint": endpoint_names[sheet.title],
                "value": "" if missing else value,
                "missing": missing,
                "source_sheet": sheet.title,
                "source_row": source_row,
                "source_cell": f"C{source_row}",
                "source_file": "supplementary_data_8.xlsx",
                "source_doi": "10.1038/s43856-022-00209-1",
                "dose_unit": "x_unbound_cmax",
                "response_unit": "percent_source_normalised" if sheet.title == "ALBUMIN" else "source_units",
                "chip_id": "",
                "sample_id": "",
                "run_id": "",
                "donor_id": "",
                "pairing_status": "unknown",
                "missing_reason": "not_reported" if missing else "",
                "measurement_kind": "original",
            })

    output_path = ROOT / "data" / "measurements.csv"
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    print(f"Prepared {len(records)} endpoint rows, preserving missing values and source rows.")
    return records


if __name__ == "__main__":
    prepare_data()
