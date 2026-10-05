"""Reproduce the real-data audit, fixed simulations, comparison tables and demo."""

from pathlib import Path
import csv
import json
import platform
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import scipy

from prepare_data import prepare_data
from auditor import analyse_evidence, audit_sources, conclusion_changed, dose_samples, fit_curve, predict_curve, MODEL_NAMES
from model import find_crossing

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "results" / "auditor"
PAIRS = [["Clozapine", "Olanzapine"], ["Troglitazone", "Pioglitazone"], ["Trovafloxacin", "Levofloxacin"]]
WARNING_NAMES = ["no_warning", "count_warning", "source_warning", "sensitivity_warning", "full_warning", "legacy_sensitivity_warning", "legacy_full_warning"]


def write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            exported = {}
            for field, value in row.items():
                exported[field] = json.dumps(value) if isinstance(value, (list, dict)) else value
            writer.writerow(exported)


def decision_metrics(rows):
    metrics = {}
    for name in WARNING_NAMES:
        true_positive = false_positive = true_negative = false_negative = 0
        retained_errors = []
        for row in rows:
            flagged = row[name]
            event = row["reference_event"]
            if flagged and event:
                true_positive += 1
            elif flagged:
                false_positive += 1
            elif event:
                false_negative += 1
            else:
                true_negative += 1
            if not flagged and row.get("absolute_error_pp") is not None:
                retained_errors.append(row["absolute_error_pp"])
        flagged_count = true_positive + false_positive
        event_count = true_positive + false_negative
        retained = true_negative + false_negative
        metrics[name] = {"n": len(rows), "tp": true_positive, "fp": false_positive, "tn": true_negative, "fn": false_negative, "precision": true_positive / flagged_count if flagged_count else None, "recall": true_positive / event_count if event_count else None, "retained_fraction": retained / len(rows), "retained_mae_pp": float(np.mean(retained_errors)) if retained_errors else None}
    return metrics


def evaluate_real(records, full_analysis):
    rows = []
    doses, samples = dose_samples(records)
    for held_dose in doses[1:-1]:
        training = [row for row in records if row["dose_cmax_multiple"] != held_dose]
        analysis = analyse_evidence(training)
        held = [row["value"] for row in records if row["dose_cmax_multiple"] == held_dose and not row["missing"]]
        observed_mean = float(np.mean(held))
        result = {"compound": records[0]["compound"], "held_dose": float(held_dose), "training_doses": analysis["doses"], "observed_mean": observed_mean, "no_warning": False, "count_warning": analysis["count_warning"], "source_warning": analysis["source_warning"], "sensitivity_warning": analysis["review"], "full_warning": analysis["review"] or analysis["source_warning"], "reference_event": conclusion_changed(analysis["primary"], full_analysis["primary"]), "training_state": analysis["primary"]["state"], "restored_state": full_analysis["primary"]["state"], "warning_reasons": analysis["flags"]}
        result["legacy_sensitivity_warning"] = analysis["legacy_review"]
        result["legacy_full_warning"] = analysis["legacy_review"] or analysis["source_warning"]
        result["legacy_warning_reasons"] = analysis["legacy_flags"]
        result["fit_diagnostics"] = analysis["diagnostics"]
        for curve in analysis["models"]:
            prediction = predict_curve(curve, [held_dose])
            result[curve["model"] + "_prediction"] = float(prediction[0]) if prediction is not None else None
            result[curve["model"] + "_diagnostics"] = curve["diagnostics"]
        result["absolute_error_pp"] = abs(result["isotonic_prediction"] - observed_mean)
        rows.append(result)
    return rows


def prediction_metrics(rows):
    metrics = {}
    for name in MODEL_NAMES:
        errors = []
        for row in rows:
            if row[name + "_prediction"] is not None:
                errors.append(row[name + "_prediction"] - row["observed_mean"])
        metrics[name] = {"eligible_folds": len(errors), "failed_folds": len(rows) - len(errors), "mae_pp": float(np.mean(np.abs(errors))) if errors else None, "rmse_pp": float(np.sqrt(np.mean(np.array(errors) ** 2))) if errors else None}
    return metrics


def simulate_experiment(generator, index, partition):
    scenario_names = ["clean", "random_missing", "response_dependent_missing", "truncated_range", "singletons", "influential_reading", "non_monotonic", "run_shift"]
    scenario = scenario_names[index % len(scenario_names)]
    shape = "hill" if (index // len(scenario_names)) % 2 == 0 else "piecewise"
    original_doses = np.logspace(0, 2.5, 6)
    midpoint = generator.uniform(0.8, 2.2)
    slope = generator.uniform(2.0, 5.0)
    lower = generator.uniform(5.0, 30.0)
    upper = generator.uniform(90.0, 140.0)
    run_shift = generator.normal(0, 15) if scenario == "run_shift" else 0.0

    def latent_response(doses):
        log_doses = np.log10(doses)
        if shape == "hill":
            response = lower + (upper - lower) / (1 + np.exp(slope * (log_doses - midpoint)))
        else:
            response = np.interp(log_doses, [0.0, midpoint - 0.25, midpoint + 0.25, 2.5], [upper, upper - 8, lower + 8, lower])
        if scenario == "non_monotonic":
            response = response + 45 * np.exp(-((log_doses - 1.9) / 0.3) ** 2)
        return response + run_shift

    doses = original_doses[:4] if scenario == "truncated_range" else original_doses
    records = []
    for dose_index, dose in enumerate(doses):
        repeats = 1 if scenario == "singletons" else 2
        for repeat in range(repeats):
            value = float(latent_response(np.array([dose]))[0] + generator.normal(0, 8))
            if scenario == "influential_reading" and dose_index == 3 and repeat == 0:
                value += 90
            missing = scenario == "random_missing" and generator.random() < 0.15
            if scenario == "response_dependent_missing" and value < 55:
                missing = generator.random() < 0.45
            record_id = f"{partition}_{index:03d}_{dose_index}_{repeat}"
            records.append({"data_origin": "synthetic", "source_record_id": record_id, "compound": f"sim_{index:03d}", "day": 3, "dose_cmax_multiple": float(dose), "endpoint": "albumin_percent", "value": "" if missing else value, "missing": bool(missing), "source_file": "generated", "source_sheet": scenario, "source_row": len(records) + 1, "source_cell": record_id, "source_doi": "", "dose_unit": "x_unbound_cmax", "response_unit": "percent_source_normalised", "chip_id": "sim_chip_" + record_id, "sample_id": "sim_sample_" + record_id, "run_id": f"sim_run_{partition}_{index:03d}", "donor_id": "", "pairing_status": "not_applicable", "missing_reason": scenario if missing else "", "measurement_kind": "original"})
    observed_doses, samples = dose_samples(records)
    truth_doses = np.logspace(np.log10(observed_doses[0]), np.log10(observed_doses[-1]), 2001)
    crossing, state = find_crossing(truth_doses, latent_response(truth_doses))
    return records, {"scenario": scenario, "shape": shape, "state": state, "crossing": crossing}


def evaluate_synthetic(seed, partition):
    generator = np.random.default_rng(seed)
    results = []
    measurements = []
    for index in range(96):
        records, truth = simulate_experiment(generator, index, partition)
        analysis = analyse_evidence(records)
        measurements.extend(records)
        primary = analysis["primary"]
        results.append({"partition": partition, "experiment": index, "scenario": truth["scenario"], "shape": truth["shape"], "true_state": truth["state"], "estimated_state": primary["state"], "true_crossing": truth["crossing"], "estimated_crossing": primary["crossing"], "reference_event": conclusion_changed(truth, primary), "no_warning": False, "count_warning": analysis["count_warning"], "source_warning": analysis["source_warning"], "sensitivity_warning": analysis["review"], "full_warning": analysis["review"] or analysis["source_warning"], "warning_reasons": analysis["flags"]})
        results[-1]["legacy_sensitivity_warning"] = analysis["legacy_review"]
        results[-1]["legacy_full_warning"] = analysis["legacy_review"] or analysis["source_warning"]
        results[-1]["fit_diagnostics"] = analysis["diagnostics"]
    write_csv(OUTPUT / f"synthetic_{partition}_measurements.csv", measurements)
    write_csv(OUTPUT / f"synthetic_{partition}_results.csv", results)
    return results


def fault_cases(clean_records):
    examples = []
    for name, expected in [("clean", None), ("wrong_dose_unit", "incompatible_dose_unit"), ("wrong_response_unit", "incompatible_response_unit"), ("duplicate", "duplicate_source_record"), ("derived", "derived_observation"), ("unsafe_pairing", "unsupported_pairing")]:
        records = [row.copy() for row in clean_records]
        if name == "wrong_dose_unit":
            records[0]["dose_unit"] = "micromolar"
        elif name == "wrong_response_unit":
            records[0]["response_unit"] = "mg_per_day"
        elif name == "duplicate":
            records.append(records[0].copy())
        elif name == "derived":
            records[0]["measurement_kind"] = "derived_auc"
        issues = audit_sources(records, require_pairing=name == "unsafe_pairing")
        blocked_codes = sorted(set(issue["code"] for issue in issues if issue["severity"] == "blocked"))
        examples.append({"case": name, "expected_code": expected, "detected_codes": blocked_codes, "passed": expected in blocked_codes if expected else not blocked_codes})
    return examples


def create_plots(drugs, metrics):
    colours = {"isotonic": "#17685c", "raw_interpolation": "#bc7831", "logistic": "#5159a5"}
    figure, axes = plt.subplots(3, 2, figsize=(11, 12), sharex=True)
    for axis, drug in zip(axes.flat, drugs):
        for row in drug["records"]:
            if not row["missing"]:
                axis.scatter(row["dose_cmax_multiple"], row["value"], color="#59636d", s=24, alpha=0.7)
        plot_doses = np.logspace(np.log10(drug["doses"][0]), np.log10(drug["doses"][-1]), 200)
        for curve in drug["models"]:
            if curve["model"] in colours and curve["success"]:
                axis.plot(plot_doses, predict_curve(curve, plot_doses), label=curve["model"].replace("_", " "), color=colours[curve["model"]])
        axis.axhline(50, color="#707780", linestyle=":")
        axis.set_xscale("log")
        axis.set_title(drug["compound"] + (" - review" if drug["review"] else " - finite scenarios agree"))
        axis.set_ylabel("Normalised albumin (%)")
        axis.grid(alpha=0.15)
    axes[0, 0].legend(fontsize=8)
    for axis in axes[-1]:
        axis.set_xlabel("Dose / unbound Cmax")
    figure.suptitle("Published day-three liver-chip data: observations and model assumptions", y=0.99)
    figure.tight_layout()
    figure.savefig(OUTPUT / "dose_response_comparison.png", dpi=160)
    plt.close(figure)
    figure, axis = plt.subplots(figsize=(7, 4))
    names = list(metrics)
    axis.bar([name.replace("_", "\n") for name in names], [metrics[name]["mae_pp"] for name in names], color=["#17685c", "#bc7831", "#90959b", "#5159a5"])
    axis.set_ylabel("Held-dose MAE (percentage points)")
    axis.set_title("Same 23 interior dose conditions; correlated within six drugs")
    figure.tight_layout()
    figure.savefig(OUTPUT / "held_dose_comparison.png", dpi=160)
    plt.close(figure)


def run_auditor():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    all_records = prepare_data()
    albumin = [row for row in all_records if row["endpoint"] == "albumin_percent"]
    data_ready = time.perf_counter()
    drugs = []
    held_rows = []
    scenario_rows = []
    source_issues = []
    checklist_rows = []
    for compound in sorted(set(row["compound"] for row in albumin)):
        records = [row for row in albumin if row["compound"] == compound]
        analysis = analyse_evidence(records)
        analysis["compound"] = compound
        analysis["records"] = records
        drugs.append(analysis)
        held_rows.extend(evaluate_real(records, analysis))
        for row in analysis["scenarios"]:
            scenario_rows.append({"compound": compound, **row})
        for issue in analysis["issues"]:
            source_issues.append({"compound": compound, **issue})
        for item in analysis["checklist"]:
            checklist_rows.append({"compound": compound, **item})
    real_finished = time.perf_counter()
    development = evaluate_synthetic(20261001, "development")
    evaluation = evaluate_synthetic(20261002, "evaluation")
    revision = evaluate_synthetic(20261004, "revision_evaluation")
    faults = fault_cases(drugs[0]["records"])
    metrics = prediction_metrics(held_rows)
    per_compound = {}
    for drug in drugs:
        subset = [row for row in held_rows if row["compound"] == drug["compound"]]
        per_compound[drug["compound"]] = {"prediction": prediction_metrics(subset), "warnings": decision_metrics(subset)}
    summary = {"date": "2026-10-04", "category": "Tool & Platform", "endpoint": "day-three normalised albumin", "real_albumin_readings": len(albumin), "real_observed_albumin_readings": sum(not row["missing"] for row in albumin), "real_drugs": len(drugs), "real_dose_conditions": sum(len(drug["doses"]) for drug in drugs), "real_held_conditions": len(held_rows), "real_prediction": metrics, "real_warnings": decision_metrics(held_rows), "per_compound": per_compound, "synthetic_development": decision_metrics(development), "synthetic_evaluation": decision_metrics(evaluation), "synthetic_revision_evaluation": decision_metrics(revision), "synthetic_seeds": {"development": 20261001, "evaluation": 20261002, "revision_evaluation": 20261004}, "synthetic_experiments_per_partition": 96, "fault_cases_passed": sum(row["passed"] for row in faults), "fault_cases_total": len(faults), "core_real_analysis_seconds": real_finished - data_ready, "analysis_seconds_including_simulations_excluding_exports": time.perf_counter() - data_ready, "input_seconds": data_ready - started, "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__, "matplotlib": matplotlib.__version__, "processor": platform.processor(), "system": platform.platform()}, "scope": "Exploratory within-drug evidence sensitivity, not clinical safety or independent-chip validation."}
    paired_comparison = []
    paired_decisions = []
    datasets = [("real_restoration", "Retrospective", held_rows), ("synthetic_development", "Retrospective", development), ("synthetic_evaluation", "Retrospective", evaluation), ("synthetic_revision_evaluation", "Fresh generator seed", revision)]
    for dataset, evidence_status, rows in datasets:
        decisions = decision_metrics(rows)
        for arm, name in [("A: curve only", "no_warning"), ("Legacy: diagnostics trigger review", "legacy_full_warning"), ("B: guarded report", "full_warning")]:
            paired_comparison.append({"dataset": dataset, "evidence_status": evidence_status, "arm": arm, **decisions[name]})
        for index, row in enumerate(rows):
            paired_decisions.append({"dataset": dataset, "case": index, "compound": row.get("compound", row.get("experiment")), "held_dose": row.get("held_dose"), "scenario": row.get("scenario"), "reference_event": row["reference_event"], "A_warning": row["no_warning"], "legacy_warning": row["legacy_full_warning"], "B_warning": row["full_warning"], "absolute_error_pp": row.get("absolute_error_pp"), "B_reasons": row["warning_reasons"], "fit_diagnostics": row["fit_diagnostics"]})
    summary["paired_comparison"] = paired_comparison
    output = {"summary": summary, "pairs": PAIRS, "drug_results": drugs, "held_dose_predictions": held_rows, "synthetic_evaluation_results": evaluation, "synthetic_revision_evaluation_results": revision, "fault_cases": faults}
    write_csv(OUTPUT / "held_dose_predictions.csv", held_rows)
    write_csv(OUTPUT / "conclusion_scenarios.csv", scenario_rows)
    write_csv(OUTPUT / "source_issues.csv", source_issues)
    write_csv(OUTPUT / "fault_cases.csv", faults)
    write_csv(OUTPUT / "evidence_checklist.csv", checklist_rows)
    write_csv(OUTPUT / "paired_ab_comparison.csv", paired_comparison)
    write_csv(OUTPUT / "paired_ab_decisions.csv", paired_decisions)
    (OUTPUT / "results.json").write_text(json.dumps(output, indent=2, allow_nan=False), encoding="utf-8")
    create_plots(drugs, metrics)
    template_path = ROOT / "auditor_template.html"
    if template_path.exists():
        (ROOT / "auditor_demo.html").write_text(template_path.read_text(encoding="utf-8").replace("__AUDITOR_JSON__", json.dumps(output, allow_nan=False)), encoding="utf-8")
    planner_template = ROOT / "planner_template.html"
    if planner_template.exists():
        (ROOT / "planner.html").write_text(planner_template.read_text(encoding="utf-8").replace("__AUDITOR_JSON__", json.dumps(output, allow_nan=False)), encoding="utf-8")
    validation_template = ROOT / "validation_template.html"
    if validation_template.exists():
        (ROOT / "validation.html").write_text(validation_template.read_text(encoding="utf-8").replace("__SUMMARY_JSON__", json.dumps(summary, allow_nan=False)), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key not in ["per_compound"]}, indent=2))
    for drug in drugs:
        print(drug["compound"], drug["primary"]["state"], drug["primary"]["crossing"], drug["flags"])
    return output


if __name__ == "__main__":
    run_auditor()
