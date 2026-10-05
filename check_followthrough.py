"""Check documented revisions using explicitly synthetic follow-up fixtures."""

from copy import deepcopy
from pathlib import Path
import csv
import io
import json

from followthrough import reassess_case

ROOT = Path(__file__).resolve().parent
REFERENCE = "Synthetic QA fixture; not an experimental correction or new measurement."
COMPATIBILITY = "Synthetic fixture retains day 3, x_unbound_cmax and percent_source_normalised; biological comparability is not verified."


def as_csv(records):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(records[0]))
    writer.writeheader()
    writer.writerows(records)
    return buffer.getvalue()


def rejected(baseline, revised, expected, action=None, action_doses=None):
    try:
        reassess_case(baseline, as_csv(revised), REFERENCE, COMPATIBILITY, action, action_doses)
    except ValueError as error:
        assert expected in str(error), str(error)
    else:
        raise AssertionError("An incompatible revision was accepted: " + expected)


def main():
    results = json.loads((ROOT / "results/auditor/results.json").read_text(encoding="utf-8"))
    cases = {case["compound"]: case for case in results["drug_results"]}
    original = cases["Clozapine"]["records"]
    frozen = json.dumps(original, sort_keys=True)
    revised = deepcopy(original)
    target = next(row for row in revised if row["source_cell"] == "C12")
    target["value"] = 40.0
    target["data_origin"] = "synthetic_followthrough_fixture"
    corrected = reassess_case(original, as_csv(revised), REFERENCE, COMPATIBILITY)
    assert corrected["baseline"]["primary"]["state"] == "right_censored"
    assert corrected["updated"]["primary"]["state"] == "within_range"
    assert corrected["material_conclusion_change"]
    assert corrected["record_changes"][0]["source_record_id"] == target["source_record_id"]
    assert len(corrected["record_changes"]) == 1
    assert next(row for row in corrected["baseline"]["records"] if row["source_cell"] == "C12")["value"] == next(row for row in original if row["source_cell"] == "C12")["value"]
    assert len([item for item in corrected["updated"]["checklist"] if item["status"] == "Not assessed"]) == 5
    assert json.dumps(original, sort_keys=True) == frozen

    pioglitazone = cases["Pioglitazone"]["records"]
    recovered = deepcopy(pioglitazone)
    row = next(row for row in recovered if row["source_cell"] == "C39")
    row.update(value=120.0, missing=False, data_origin="synthetic_followthrough_fixture")
    result = reassess_case(pioglitazone, as_csv(recovered), REFERENCE, COMPATIBILITY)
    assert sum(row["missing"] for row in result["baseline"]["records"]) == 2
    assert sum(row["missing"] for row in result["updated"]["records"]) == 1
    assert result["record_changes"][0]["kind"] == "recovered"
    assert reassess_case(pioglitazone, as_csv(recovered), REFERENCE, COMPATIBILITY, "RECOVER")["measurements_changed"]

    added = deepcopy(original)
    new_row = dict(original[0], source_record_id="synthetic_followthrough_test_reading", source_file="synthetic_QA.csv", source_sheet="QA", source_cell="B2", source_row="2", source_doi="", value=125.0, data_origin="synthetic_followthrough_fixture")
    added.append(new_row)
    result = reassess_case(original, as_csv(added), REFERENCE, COMPATIBILITY)
    assert result["record_changes"][0]["kind"] == "added"
    assert len(result["updated"]["records"]) == len(original) + 1
    assert reassess_case(original, as_csv(added), REFERENCE, COMPATIBILITY, "REPEAT", [1.0])["measurements_changed"]
    rejected(original, added, "named existing dose", "REPEAT", [300.0])
    extended = deepcopy(added)
    extended[-1]["dose_cmax_multiple"] = 600.0
    assert reassess_case(original, as_csv(extended), REFERENCE, COMPATIBILITY, "EXTEND")["measurements_changed"]
    metadata = deepcopy(original)
    metadata[0]["source_file"] = "synthetic_QA_reference_revision.csv"
    result = reassess_case(original, as_csv(metadata), REFERENCE, COMPATIBILITY, "INSPECT")
    assert result["evidence_version_changed"] and not result["measurements_changed"]
    rejected(original, metadata, "added observed original", "REPEAT", [300.0])
    rejected(original, metadata, "new-dose outcome", "EXTEND")
    metadata = deepcopy(pioglitazone)
    metadata[0]["source_file"] = "synthetic_QA_reference_revision.csv"
    rejected(pioglitazone, metadata, "missing baseline original", "RECOVER")

    rejected(original, [row for row in revised if row["source_cell"] != "C12"], "Retain every baseline")
    missing = deepcopy(revised)
    next(row for row in missing if row["source_cell"] == "C12").update(missing=True, value="")
    rejected(original, missing, "cannot be changed to missing")
    rejected(original, revised + [revised[0]], "same source record")
    rejected(original, pioglitazone, "no albumin records for Clozapine")
    rejected(original, original, "No changed or added records")
    for field, value, message in [("dose_unit","mg_per_l","multiples of unbound Cmax"),("day",4,"day-three"),("measurement_kind","derived","derived summary")]:
        incompatible = deepcopy(revised)
        incompatible[0][field] = value
        rejected(original, incompatible, message)
    fixed = reassess_case(original + [original[0]], as_csv(original), REFERENCE, COMPATIBILITY)
    assert fixed["baseline"]["blocked"] and not fixed["updated"]["blocked"]
    assert fixed["record_changes"][0]["fields"][0]["field"] == "input_occurrences"
    print("Synthetic revision checks passed: correction, recovery, new reading, provenance retention, blocked-input repair and incompatible/deleted/missing evidence rejection.")


if __name__ == "__main__":
    main()
