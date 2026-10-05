"""Run the real-data pilot and export results plus a standalone local demo."""

from pathlib import Path
import csv
import json
import time
import numpy as np

from prepare_data import prepare_data
from model import analyse_albumin, evaluate_held_doses

ROOT = Path(__file__).resolve().parent


def run_experiment():
    measurements = prepare_data()
    compounds = sorted(set(row["compound"] for row in measurements))
    random_generator = np.random.default_rng(42)
    results = []
    held_dose_predictions = []
    started = time.perf_counter()

    for compound in compounds:
        albumin_rows = []
        for row in measurements:
            if row["compound"] == compound and row["endpoint"] == "albumin_percent":
                albumin_rows.append(row)
        doses = sorted(set(row["dose_cmax_multiple"] for row in albumin_rows))
        samples_by_dose = []
        for dose in doses:
            samples = []
            for row in albumin_rows:
                if row["dose_cmax_multiple"] == dose and not row["missing"]:
                    samples.append(row["value"])
            if not samples:
                raise ValueError(f"No observed albumin values for {compound}, dose {dose}")
            samples_by_dose.append(np.array(samples))

        result = analyse_albumin(doses, samples_by_dose, random_generator)
        result["compound"] = compound
        endpoint_summaries = []
        for dose in doses:
            summary = {"dose_cmax_multiple": dose}
            for endpoint in ["albumin_percent", "alt_source_units", "morphology_score"]:
                values = []
                missing_count = 0
                for row in measurements:
                    if row["compound"] == compound and row["dose_cmax_multiple"] == dose and row["endpoint"] == endpoint:
                        if row["missing"]:
                            missing_count += 1
                        else:
                            values.append(row["value"])
                summary[endpoint] = {
                    "mean": float(np.mean(values)) if values else None,
                    "observed_count": len(values),
                    "missing_count": missing_count,
                }
            endpoint_summaries.append(summary)
        # Endpoint sheets are aggregated independently, without inventing paired chip IDs.
        result["endpoint_summaries"] = endpoint_summaries
        results.append(result)
        compound_predictions = evaluate_held_doses(doses, samples_by_dose, random_generator)
        for row in compound_predictions:
            row["compound"] = compound
            held_dose_predictions.append(row)

    metrics = {}
    for name in ["monotone", "raw_interpolation", "constant"]:
        errors = []
        for row in held_dose_predictions:
            errors.append(row[f"{name}_prediction"] - row["observed_albumin_mean"])
        errors = np.array(errors)
        metrics[name] = {
            "mae_pp": float(np.mean(np.abs(errors))),
            "rmse_pp": float(np.sqrt(np.mean(errors ** 2))),
        }
    covered = sum(row["resampling_range_contains_mean"] for row in held_dose_predictions)
    summary = {
        "endpoint_rows": len(measurements),
        "observed_endpoint_rows": sum(not row["missing"] for row in measurements),
        "missing_endpoint_rows": sum(row["missing"] for row in measurements),
        "compounds": len(compounds),
        "drug_dose_conditions": sum(len(result["doses"]) for result in results),
        "held_interior_dose_conditions": len(held_dose_predictions),
        "metrics": metrics,
        "resampling_range_covered_conditions": covered,
        "resampling_range_coverage": covered / len(held_dose_predictions),
        "analysis_seconds_excluding_download_and_export": time.perf_counter() - started,
        "seed": 42,
        "bootstrap_draws": 500,
        "scope": "Within-drug day-three albumin dose interpolation; no donor or new-drug validation.",
    }
    output_directory = ROOT / "results"
    output_directory.mkdir(exist_ok=True)
    output = {"summary": summary, "drug_results": results, "held_dose_predictions": held_dose_predictions}
    with (output_directory / "results.json").open("w", encoding="utf-8") as file:
        json.dump(output, file, indent=2, allow_nan=False)
    with (output_directory / "held_dose_predictions.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(held_dose_predictions[0]))
        writer.writeheader()
        writer.writerows(held_dose_predictions)
    template = (ROOT / "demo_template.html").read_text(encoding="utf-8")
    demo = template.replace("__RESULTS_JSON__", json.dumps(output, allow_nan=False))
    (ROOT / "demo.html").write_text(demo, encoding="utf-8")
    print(json.dumps(summary, indent=2))
    for result in results:
        print(result["compound"], result["decision"], result["albumin_50_crossing"])
    return output


if __name__ == "__main__":
    run_experiment()
