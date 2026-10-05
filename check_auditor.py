"""Check provenance, fold isolation, input rejection and final artifact values."""

from pathlib import Path
import json
import numpy as np
import openpyxl

from auditor import analyse_evidence, audit_sources, conclusion_changed, fit_curve
from prepare_data import prepare_data
from model import find_crossing

ROOT = Path(__file__).resolve().parent


def assert_numeric_equivalent(actual, expected):
    """Allow numerical-library rounding while preserving all discrete results."""
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            assert_numeric_equivalent(actual[key], expected[key])
    elif isinstance(expected, float):
        np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-6)
    else:
        assert actual == expected


records = prepare_data()
albumin = [row for row in records if row["endpoint"] == "albumin_percent"]
assert len(records) == 210 and len(albumin) == 70
assert sum(row["missing"] for row in albumin) == 2
assert len(set(row["source_record_id"] for row in records)) == 210
assert all(row["chip_id"] == "" and row["run_id"] == "" for row in records)
workbook = openpyxl.load_workbook(ROOT / "data/raw/supplementary_data_8.xlsx", data_only=True)
for row in records:
    value = workbook[row["source_sheet"]][row["source_cell"]].value
    if row["missing"]:
        assert row["value"] == "" and (value is None or str(value).strip().lower() in ["na", "nan"])
    else:
        assert float(value) == row["value"]

clean = [row for row in albumin if row["compound"] == "Trovafloxacin"]
original = analyse_evidence(clean)
assert not original["review"] and original["legacy_review"]
assert original["diagnostics"] and "logistic_fit_diagnostic" not in original["flags"]
statuses = {item["code"]: item["status"] for item in original["checklist"]}
assert statuses["assay_controls"] == "Not assessed"
assert statuses["device_qc"] == "Not assessed"
assert statuses["experimental_independence"] == "Not assessed"
assert statuses["threshold_bracket"] == "Pass"
renamed = []
for index, row in enumerate(reversed(clean)):
    renamed.append({**row, "source_record_id": f"different_record_{index}"})
changed = analyse_evidence(renamed)
assert np.allclose(original["primary"]["fitted"], changed["primary"]["fitted"])
assert original["flags"] == changed["flags"]
assert np.isclose(original["primary"]["crossing"], changed["primary"]["crossing"])
assert any(issue["code"] == "unsupported_pairing" for issue in audit_sources(clean, require_pairing=True))
for field, value, expected in [("dose_unit", "micromolar", "incompatible_dose_unit"), ("response_unit", "mg", "incompatible_response_unit"), ("measurement_kind", "derived_auc", "derived_observation"), ("day", 7, "incompatible_timepoint"), ("endpoint", "alt_source_units", "incompatible_endpoint"), ("source_record_id", "", "missing_source_record_id")]:
    invalid = [row.copy() for row in clean]
    invalid[0][field] = value
    result = analyse_evidence(invalid)
    assert result["blocked"] and any(issue["code"] == expected for issue in result["issues"])
assert analyse_evidence(clean + [clean[0].copy()])["blocked"]
assert analyse_evidence([clean[0], {**clean[1], "compound": "Other compound"}])["blocked"]
assert find_crossing([1, 10], [100, 0]) == (np.sqrt(10), "within_range")
assert find_crossing([1, 10], [100, 60]) == (None, "right_censored")
assert find_crossing([1, 10], [50, 40]) == (None, "left_censored")
assert find_crossing([1, 10], [100, 50]) == (10.0, "within_range")
raw_curve = fit_curve(np.array([1., 10., 100.]), [np.array([100.]), np.array([40.]), np.array([80.])], "raw_interpolation")
assert raw_curve["state"] == "within_range"
assert np.isclose(raw_curve["crossing"], 10 ** (50 / 60))
assert raw_curve["diagnostics"] == ["threshold_recrossing"]
repeated_curve = fit_curve(np.array([1., 10., 100., 1000.]), [np.array([100.]), np.array([40.]), np.array([80.]), np.array([30.])], "raw_interpolation")
assert np.isclose(repeated_curve["crossing"], raw_curve["crossing"])
assert repeated_curve["diagnostics"] == ["multiple_downward_crossings"]
assert not conclusion_changed({"state": "within_range", "crossing": 10}, {"state": "within_range", "crossing": 20})
assert conclusion_changed({"state": "within_range", "crossing": 10}, {"state": "within_range", "crossing": 20.1})
curve = fit_curve(np.array([1., 10., 100.]), [np.array([100]), np.array([50]), np.array([0])], "logistic")
assert not curve["success"] and curve["state"] == "fit_failed"

output = json.loads((ROOT / "results/auditor/results.json").read_text(encoding="utf-8"))
assert len(output["held_dose_predictions"]) == 23
for fold in output["held_dose_predictions"]:
    assert fold["held_dose"] not in fold["training_doses"]
    training = [row for row in albumin if row["compound"] == fold["compound"] and row["dose_cmax_multiple"] != fold["held_dose"]]
    result = analyse_evidence(training)
    assert result["review"] == fold["sensitivity_warning"]
    assert result["flags"] == fold["warning_reasons"]
    assert result["primary"]["state"] == fold["training_state"]
assert all(row["passed"] for row in output["fault_cases"])
assert len(output["synthetic_evaluation_results"]) == 96
assert len(output["synthetic_revision_evaluation_results"]) == 96
assert output["summary"]["synthetic_seeds"]["revision_evaluation"] == 20261004
assert len(output["summary"]["paired_comparison"]) == 12
legacy = json.loads((ROOT / "results/auditor/legacy_results_20261002.json").read_text(encoding="utf-8"))
assert_numeric_equivalent(output["summary"]["real_prediction"], legacy["summary"]["real_prediction"])
assert_numeric_equivalent(output["summary"]["real_warnings"]["legacy_full_warning"], legacy["summary"]["real_warnings"]["full_warning"])
assert_numeric_equivalent(output["summary"]["synthetic_evaluation"]["legacy_full_warning"], legacy["summary"]["synthetic_evaluation"]["full_warning"])
for current_fold, legacy_fold in zip(output["held_dose_predictions"], legacy["held_dose_predictions"]):
    assert current_fold["compound"] == legacy_fold["compound"] and current_fold["held_dose"] == legacy_fold["held_dose"]
    assert current_fold["legacy_warning_reasons"] == legacy_fold["warning_reasons"]
    assert current_fold["reference_event"] == legacy_fold["reference_event"]
clozapine = next(drug for drug in output["drug_results"] if drug["compound"] == "Clozapine")
assert len(clozapine["influential_observations"]) == 1
influence = clozapine["influential_observations"][0]
source_id = influence["source_record_ids"][0]
removed = next(row for row in clozapine["records"] if row["source_record_id"] == source_id)
assert influence["affected_values"] == [removed["value"]]
assert influence["source_cells"] == [removed["source_sheet"] + "!" + removed["source_cell"]]
remaining = [row for row in clozapine["records"] if row["source_record_id"] != source_id]
temporary = analyse_evidence(remaining)
assert temporary["primary"]["state"] == influence["state"]
assert np.isclose(temporary["primary"]["crossing"], influence["crossing"])
assert len(clozapine["records"]) == len(next(drug for drug in legacy["drug_results"] if drug["compound"] == "Clozapine")["records"])
assert output["summary"]["real_prediction"]["isotonic"]["eligible_folds"] == 23
demo = (ROOT / "auditor_demo.html").read_text(encoding="utf-8")
assert "__AUDITOR_JSON__" not in demo and '"real_held_conditions": 23' in demo
cases = {drug["compound"]: drug for drug in output["drug_results"]}
for drug in cases.values():
    source_ids = {row["source_record_id"] for row in drug["records"]}
    scenario_ids = {row["scenario_id"] for row in drug["scenarios"]}
    assert len(scenario_ids) == len(drug["scenarios"])
    for action in drug["recommendations"]:
        assert set(action["source_record_ids"]) <= source_ids
        assert set(action["scenario_ids"]) <= scenario_ids
    assert drug["unassessed_evidence"] == [item["code"] for item in drug["checklist"] if item["status"] == "Not assessed" and item["layer"] == "evidence"]

clozapine_action = cases["Clozapine"]["recommendations"][0]
assert clozapine_action["rule"] == "reading_influence"
assert clozapine_action["source_record_ids"] == ["ewart2022_supp8_ALBUMIN_C12"]
assert "69.68%" in clozapine_action["reason"] and "256.22" in clozapine_action["reason"]
pioglitazone = cases["Pioglitazone"]
assert [item["rule"] for item in pioglitazone["recommendations"]] == ["reading_influence", "missing_evidence"]
assert len(pioglitazone["recommendations"][0]["scenario_ids"]) == 2
assert "bracketing coverage" in pioglitazone["recommendations"][0]["reason"]
assert "None of the 10" in pioglitazone["recommendations"][1]["reason"]
assert pioglitazone["recommendations"][1]["dose_cmax_multiples"] == [1., 3.]
troglitazone = cases["Troglitazone"]
assert [item["rule"] for item in troglitazone["recommendations"]] == ["dose_dependence", "dose_coverage"]
assert "162.38" in troglitazone["recommendations"][0]["reason"] and "64.14" in troglitazone["recommendations"][0]["reason"]
assert troglitazone["recommendations"][1]["dose_cmax_multiples"] == [294.72]
for name in ["Levofloxacin", "Olanzapine"]:
    assert [item["rule"] for item in cases[name]["recommendations"]] == ["censored_result"]
    assert "If a finite crossing is required" in cases[name]["recommendations"][0]["action"]
assert cases["Trovafloxacin"]["recommendations"][0]["rule"] == "finite_scope"

reordered = analyse_evidence(list(reversed(cases["Clozapine"]["records"])))
assert {item["scenario_id"] for item in reordered["scenarios"]} == {item["scenario_id"] for item in cases["Clozapine"]["scenarios"]}
assert reordered["recommendations"][0]["source_record_ids"] == clozapine_action["source_record_ids"]
renamed_influence = [{**row, "source_record_id": "uploaded_" + row["source_record_id"]} for row in cases["Clozapine"]["records"]]
assert analyse_evidence(renamed_influence)["recommendations"][0]["source_record_ids"] == ["uploaded_ewart2022_supp8_ALBUMIN_C12"]

# These are constructed edge cases, not additional published measurements.
fixture = []
for index, (dose, value) in enumerate([(1., 100.), (1., 100.), (10., 80.), (10., 80.), (100., 100.), (100., None)]):
    fixture.append({**clean[0], "source_record_id": f"fixture_{index}", "dose_cmax_multiple": dose, "value": "" if value is None else value, "missing": value is None})
edge = analyse_evidence(fixture)
assert "missing_probe" in edge["flags"]
assert next(item for item in edge["recommendations"] if item["rule"] == "missing_evidence")["workflow_order"] == 2
assert any(item["rule"] == "comparator_limit" for item in edge["recommendations"])
left = analyse_evidence([{**row, "missing": False, "value": 20.} for row in fixture])
assert left["primary"]["state"] == "left_censored"
assert "lower-dose coverage" in next(item for item in left["recommendations"] if item["rule"] == "censored_result")["action"]
blocked = analyse_evidence(clean + [clean[0].copy()])
assert [item["rule"] for item in blocked["recommendations"]] == ["input_fault"]

print("Verified source cells, original numerical checks, source-specific actions, dose-coverage interpretation, missing probes, failed comparators, stable links and input rejection.")
