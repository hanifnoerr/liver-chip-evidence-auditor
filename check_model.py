"""Check scientific boundaries and the exported real-data experiment."""

import json
from pathlib import Path
import numpy as np
from model import find_crossing, fit_decreasing_response, analyse_albumin

fitted = fit_decreasing_response([100, 80, 90, 40], [2, 1, 3, 2])
assert np.allclose(fitted, [100, 87.5, 87.5, 40])
assert np.all(np.diff(fitted) <= 0)
crossing, state = find_crossing([1, 10], [100, 0])
assert np.isclose(crossing, np.sqrt(10)) and state == "within_range"
assert find_crossing([1, 10], [100, 60]) == (None, "right_censored")
assert find_crossing([1, 10], [40, 20]) == (None, "left_censored")

# A constant resampling range from singleton observations must not earn a stable status.
example = analyse_albumin([1, 10], [np.array([100]), np.array([0])], np.random.default_rng(42))
assert example["decision"] == "crossing_requires_review"

root = Path(__file__).resolve().parent
results = json.loads((root / "results" / "results.json").read_text(encoding="utf-8"))
summary = results["summary"]
assert summary["endpoint_rows"] == 210
assert summary["missing_endpoint_rows"] == 6
assert summary["compounds"] == 6 and summary["drug_dose_conditions"] == 35
assert summary["held_interior_dose_conditions"] == 23
for prediction in results["held_dose_predictions"]:
    held_dose = prediction["dose_cmax_multiple"]
    training_doses = prediction["training_doses"]
    assert held_dose not in training_doses
    assert min(training_doses) < held_dose < max(training_doses)
for drug in results["drug_results"]:
    assert np.all(np.diff(drug["fitted_albumin"]) <= 0)
    if drug["censoring"] != "within_range":
        assert drug["albumin_50_crossing"] is None
print("Checked weighted pooling, log-dose crossing, censoring, singleton review, source counts, and held-dose separation.")
