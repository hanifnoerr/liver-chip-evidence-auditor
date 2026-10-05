"""Trace source limitations and test sensitivity of a 50% albumin crossing."""

import numpy as np
from scipy.optimize import least_squares
from scipy.special import expit

from model import fit_decreasing_response, find_crossing

MODEL_NAMES = ["isotonic", "raw_interpolation", "constant", "logistic"]
MISSING_PROBES = [0.0, 50.0, 100.0, 150.0, 200.0]
LOCATION_FACTOR = 2.0


def audit_sources(records, require_pairing=False):
    issues = []
    seen = set()
    for row in records:
        record_id = row["source_record_id"]
        checks = []
        if not record_id:
            checks.append(("missing_source_record_id", "blocked", "A unique source-record ID is required for traceability."))
        if float(row["day"]) != 3.0:
            checks.append(("incompatible_timepoint", "blocked", "This release analyses day-three responses only."))
        if row["endpoint"] != "albumin_percent":
            checks.append(("incompatible_endpoint", "blocked", "This analysis accepts albumin percentage records only."))
        if record_id in seen:
            checks.append(("duplicate_source_record", "blocked", "The same source record occurs twice."))
        seen.add(record_id)
        if row["dose_unit"] != "x_unbound_cmax":
            checks.append(("incompatible_dose_unit", "blocked", "This endpoint analysis expects multiples of unbound Cmax."))
        if row["endpoint"] == "albumin_percent" and row["response_unit"] != "percent_source_normalised":
            checks.append(("incompatible_response_unit", "blocked", "Albumin must retain its source-normalised percentage scale."))
        if not np.isfinite(row["dose_cmax_multiple"]) or row["dose_cmax_multiple"] <= 0:
            checks.append(("invalid_dose", "blocked", "Log-dose analysis requires a finite positive dose."))
        if not row["missing"] and not np.isfinite(row["value"]):
            checks.append(("invalid_response", "blocked", "An observed response must be finite."))
        if row["measurement_kind"] != "original":
            checks.append(("derived_observation", "blocked", "A derived summary cannot count as an original measurement."))
        if row["missing"]:
            checks.append(("missing_response", "review", "The source reading is missing; scenarios cannot recover it."))
        if require_pairing and (not row["sample_id"] or row["pairing_status"] != "documented"):
            checks.append(("unsupported_pairing", "blocked", "Cross-endpoint pairing needs a documented shared sample ID."))
        for code, severity, message in checks:
            issues.append({"code": code, "severity": severity, "source_record_id": record_id, "message": message})
    if any(not row["chip_id"] or not row["run_id"] for row in records):
        issues.append({"code": "unknown_experimental_identity", "severity": "limitation", "source_record_id": "dataset", "message": "Chip/run identities are unavailable. Source-record IDs cannot establish independent chips or pairing."})
    return issues


def dose_samples(records):
    doses = sorted(set(row["dose_cmax_multiple"] for row in records))
    kept_doses = []
    samples = []
    for dose in doses:
        values = []
        for row in records:
            if row["dose_cmax_multiple"] == dose and not row["missing"]:
                values.append(float(row["value"]))
        if values:
            kept_doses.append(float(dose))
            samples.append(np.array(values))
    return np.array(kept_doses), samples


def logistic_response(log_doses, parameters):
    lower, amplitude, log_midpoint, slope = parameters
    return lower + amplitude * expit(-slope * (log_doses - log_midpoint))


def fit_curve(doses, samples, name):
    means = np.array([float(np.mean(values)) for values in samples])
    counts = np.array([len(values) for values in samples])
    log_doses = np.log10(doses)
    result = {"model": name, "success": True, "diagnostics": [], "parameters": None, "doses": doses.tolist()}
    if name == "isotonic":
        fitted = fit_decreasing_response(means, counts)
    elif name == "raw_interpolation":
        fitted = means
    elif name == "constant":
        fitted = np.full(len(doses), np.average(means, weights=counts))
    elif name == "logistic":
        if len(doses) < 4:
            return {**result, "success": False, "diagnostics": ["fewer_than_four_doses"], "fitted": None, "crossing": None, "state": "fit_failed"}
        upper_level = max(200.0, float(np.max(means)) * 3.0 + 100.0)
        lower_bounds = [0.0, 0.0, float(log_doses[0] - 2), 0.1]
        upper_bounds = [upper_level, upper_level, float(log_doses[-1] + 2), 10.0]
        best_fit = None
        for offset in [-0.5, 0.0, 0.5]:
            initial = [max(0.1, float(np.min(means)) * 0.5), max(1.0, float(np.max(means) - np.min(means))), float(np.mean(log_doses) + offset), 1.0]
            fit = least_squares(lambda parameters: np.sqrt(counts) * (logistic_response(log_doses, parameters) - means), initial, bounds=(lower_bounds, upper_bounds), max_nfev=400)
            if fit.success and (best_fit is None or fit.cost < best_fit.cost):
                best_fit = fit
        if best_fit is None:
            return {**result, "success": False, "diagnostics": ["non_convergence"], "fitted": None, "crossing": None, "state": "fit_failed"}
        result["parameters"] = best_fit.x.tolist()
        if np.any(best_fit.active_mask != 0):
            result["diagnostics"].append("parameter_at_bound")
        if np.linalg.matrix_rank(best_fit.jac) < 4 or np.linalg.cond(best_fit.jac) > 1e6:
            result["diagnostics"].append("weak_parameter_identification")
        fitted = logistic_response(log_doses, best_fit.x)
    else:
        raise ValueError(f"Unknown curve model: {name}")
    crossing, state = find_crossing(doses, fitted)
    if name == "logistic" and state == "within_range":
        lower, amplitude, midpoint, slope = result["parameters"]
        crossing_log = midpoint + np.log(amplitude / (50.0 - lower) - 1.0) / slope
        crossing = float(10 ** crossing_log)
    result["fitted"] = fitted.tolist()
    result["crossing"] = crossing
    result["state"] = state
    down_crossings = sum(means[index - 1] > 50 and means[index] <= 50 for index in range(1, len(means)))
    up_crossings = sum(means[index - 1] <= 50 and means[index] > 50 for index in range(1, len(means)))
    if name == "raw_interpolation" and down_crossings > 1:
        result["diagnostics"].append("multiple_downward_crossings")
    elif name == "raw_interpolation" and down_crossings and up_crossings:
        result["diagnostics"].append("threshold_recrossing")
    return result


def predict_curve(curve, doses):
    if not curve["success"]:
        return None
    if curve["model"] == "logistic":
        return logistic_response(np.log10(doses), curve["parameters"])
    return np.interp(np.log10(doses), np.log10(curve["doses"]), curve["fitted"])


def conclusion_changed(reference, alternative):
    if alternative["state"] == "fit_failed":
        return True
    if reference["state"] != alternative["state"]:
        return True
    if reference["crossing"] is not None and alternative["crossing"] is not None:
        log_shift = abs(np.log10(reference["crossing"] / alternative["crossing"]))
        return bool(log_shift > np.log10(LOCATION_FACTOR))
    return False


def evidence_checklist(records, issues, primary=None, models=None, scenarios=None):
    """A pass applies only to the named check, never to drug safety."""
    checklist = []
    blocked_codes = {issue["code"] for issue in issues if issue["severity"] == "blocked"}

    def add(code, layer, label, status, evidence, action):
        checklist.append({"code": code, "layer": layer, "label": label, "status": status, "evidence": evidence, "action": action})

    input_checks = [
        ("input_scope", "Day-three albumin and compatible units", ["incompatible_timepoint", "incompatible_endpoint", "incompatible_dose_unit", "incompatible_response_unit", "mixed_compounds"], "Only day-three albumin on the source percentage and unbound-Cmax scales is supported."),
        ("source_integrity", "Unique original source records", ["missing_source_record_id", "duplicate_source_record", "derived_observation"], "Record IDs identify input observations; they do not establish independent chips."),
        ("finite_values", "Finite observed values and positive doses", ["invalid_dose", "invalid_response", "insufficient_doses"], "Missing readings are excluded from fitting and retained in the source export."),
    ]
    for code, label, failures, explanation in input_checks:
        failed = any(failure in blocked_codes for failure in failures)
        status = "Fail" if failed else "Pass"
        add(code, "input", label, status, explanation, "Resolve the reported input fault before fitting." if failed else "Retain source provenance.")
    missing_count = sum(row["missing"] for row in records)
    add("complete_readings", "evidence", "All source responses observed", "Fail" if missing_count else "Pass", f"{missing_count} missing input reading(s). A missing value is not zero.", "Recover missing measurements or retain the limitation." if missing_count else "No missing response in this input.")
    identity_reported = bool(records) and all(row.get("chip_id") and row.get("run_id") and row.get("donor_id") for row in records)
    add("experimental_metadata", "evidence", "Reported chip, run and donor mapping", "Pass" if identity_reported else "Not assessed", "All identity fields are supplied; their authenticity is not verified." if identity_reported else "Complete chip/run/donor mapping is unavailable.", "Use documented experimental identities for grouped validation.")
    add("experimental_independence", "evidence", "Independent experimental units", "Not assessed", "Source records and entered IDs alone do not prove biological independence.", "Obtain the sampling design and distinguish technical from biological repeats.")
    for code, label, explanation in [
        ("assay_controls", "Vehicle and reference-control acceptance", "Raw control measurements and pre-specified assay acceptance limits are unavailable to this analysis."),
        ("assay_calibration", "Albumin assay calibration and quantification range", "Calibration, detection/quantification limits and technical failure records are not assessed."),
        ("device_qc", "Flow, bubbles and device QC", "Device logs and pre-specified engineering acceptance limits are not assessed."),
    ]:
        add(code, "evidence", label, "Not assessed", explanation, "Review assay-specific laboratory records; do not infer a pass from the fitted curve.")
    if primary is None:
        add("threshold_bracket", "sensitivity", "Finite 50% crossing bracketed", "Not assessed", "Input faults prevent endpoint fitting.", "Resolve the input faults.")
        return checklist
    bracketed = primary["state"] == "within_range"
    add("threshold_bracket", "evidence", "Finite 50% crossing bracketed", "Pass" if bracketed else "Fail", "Crossing lies inside the measured range." if bracketed else "The result is censored; no finite in-range crossing is supported.", "Report the estimated endpoint crossing." if bracketed else "Retain the censored conclusion; additional dose coverage is needed for a finite estimate.")
    for kind, label in [("model", "Alternative curve conclusions agree"), ("reading_deletion", "Conclusion survives single-reading deletion"), ("dose_deletion", "Conclusion survives single-dose deletion")]:
        tested = [scenario for scenario in scenarios if scenario["kind"] == kind]
        changed = sum(scenario["changed"] for scenario in tested)
        status = "Fail" if changed else ("Pass" if tested else "Not assessed")
        add(kind, "sensitivity", label, status, f"{changed} material change(s) in {len(tested)} finite scenarios; no calibrated probability is implied.", "Inspect affected evidence and seek an independent repeat." if changed else "Keep the finite-scenario scope explicit.")
    logistic = next(model for model in models if model["model"] == "logistic")
    add("logistic_diagnostics", "diagnostic", "Logistic numerical fit checks", "Fail" if logistic["diagnostics"] else "Pass", ", ".join(logistic["diagnostics"]) or "No specified numerical diagnostic triggered.", "Inspect the comparator; a standalone parameter diagnostic does not prove the endpoint conclusion changed.")
    return checklist


def describe_conclusion(curve):
    if curve["state"] == "within_range":
        return f"a crossing at {curve['crossing']:.2f}× unbound Cmax"
    if curve["state"] == "right_censored":
        return "no crossing in the measured range"
    if curve["state"] == "left_censored":
        return "a response already at or below 50% at the lowest measured dose"
    return "an unavailable fit"


def build_recommendations(records, issues, primary=None, scenarios=None):
    """Link a fixed review workflow to the calculated evidence; do not select optimal doses."""
    recommendations = []
    scenarios = scenarios or []

    def add(rule, key, order, title, reason, action, source_rows=None, tested=None, codes=None, interpretation=""):
        source_rows = source_rows or []
        tested = tested or []
        doses = []
        for row in source_rows:
            dose = float(row["dose_cmax_multiple"])
            if np.isfinite(dose) and dose > 0 and dose not in doses:
                doses.append(dose)
        recommendations.append({
            "id": f"{rule}:{key}", "rule": rule, "workflow_order": order,
            "title": title, "reason": reason, "action": action,
            "source_record_ids": sorted(set(row["source_record_id"] for row in source_rows if row["source_record_id"])),
            "dose_cmax_multiples": sorted(doses),
            "scenario_ids": [scenario["scenario_id"] for scenario in tested],
            "check_codes": codes or [], "interpretation": interpretation,
        })

    blocked = [issue for issue in issues if issue["severity"] == "blocked"]
    if blocked:
        affected_ids = {issue["source_record_id"] for issue in blocked}
        affected_rows = [row for row in records if row["source_record_id"] in affected_ids]
        add("input_fault", "input", 0, "Correct the input before reviewing a response",
            " ".join(issue["message"] for issue in blocked),
            "Resolve the named source or measurement fault and re-import the original measurements.",
            affected_rows, codes=["input_scope", "source_integrity", "finite_values"])
        return recommendations

    compound = records[0]["compound"]
    rows_by_id = {row["source_record_id"]: row for row in records}
    changed = [scenario for scenario in scenarios if scenario["changed"]]
    grouped_doses = set()
    reading_doses = set()
    for scenario in changed:
        if scenario["kind"] == "reading_deletion":
            reading_doses.add(rows_by_id[scenario["source_record_ids"][0]]["dose_cmax_multiple"])
    for dose in sorted(reading_doses):
        tested = []
        notes = []
        source_ids = set()
        for scenario in changed:
            if scenario["kind"] != "reading_deletion":
                continue
            row = rows_by_id[scenario["source_record_ids"][0]]
            if row["dose_cmax_multiple"] != dose:
                continue
            tested.append(scenario)
            source_ids.add(row["source_record_id"])
            notes.append(f"{row['source_sheet']}!{row['source_cell']} is {row['value']:.2f}% albumin. Its temporary removal changes {compound} from {describe_conclusion(primary)} to {describe_conclusion(scenario)}.")
        for scenario in changed:
            if scenario["kind"] == "dose_deletion" and scenario["affected_dose"] == dose:
                tested.append(scenario)
                source_ids.update(scenario["source_record_ids"])
                grouped_doses.add(dose)
                if scenario["coverage_removed"]:
                    low, high = scenario["remaining_dose_range"]
                    notes.append(f"Removing the whole {dose:g}× dose also removes bracketing coverage: the remaining doses span {low:g}–{high:g}× unbound Cmax.")
                else:
                    notes.append(f"Removing the whole {dose:g}× dose changes the result to {describe_conclusion(scenario)}.")
        source_rows = [rows_by_id[source_id] for source_id in sorted(source_ids)]
        codes = ["reading_deletion"]
        if dose in grouped_doses:
            codes.append("dose_deletion")
        add("reading_influence", repr(float(dose)), 1, f"Verify the reading at {dose:g}× unbound Cmax",
            " ".join(notes),
            "Inspect the named original measurement and available assay records. If the conclusion is needed and the concern remains unresolved, consider an independent repeat at this dose with documented sampling.",
            source_rows, tested, codes,
            "Influence does not establish a measurement error. Original readings remain included.")

    missing_rows = [row for row in records if row["missing"]]
    probes = [scenario for scenario in scenarios if scenario["kind"] == "missing_probe"]
    changed_probes = [scenario for scenario in probes if scenario["changed"]]
    if missing_rows:
        locations = []
        for row in missing_rows:
            locations.append(f"{row['source_sheet']}!{row['source_cell']} at {row['dose_cmax_multiple']:g}× unbound Cmax")
        reason = "; ".join(locations) + (" is missing. " if len(missing_rows) == 1 else " are missing. ")
        if changed_probes:
            reason += f"{len(changed_probes)} of {len(probes)} one-at-a-time hypothetical replacements change the conclusion."
        else:
            reason += f"None of the {len(probes)} tested one-at-a-time hypothetical replacements changes the current conclusion: {describe_conclusion(primary)}."
        add("missing_evidence", "responses", 2 if changed_probes else 5,
            "Locate the missing albumin measurements", reason,
            "Check whether documented original values are available. Recover them only from source records; otherwise retain missingness and its limitation.",
            missing_rows, probes, ["complete_readings"],
            "Hypothetical replacements are sensitivity probes, not recovered measurements or imputations.")

    for scenario in changed:
        if scenario["kind"] != "dose_deletion" or scenario["affected_dose"] in grouped_doses:
            continue
        dose = scenario["affected_dose"]
        source_rows = [rows_by_id[source_id] for source_id in scenario["source_record_ids"]]
        locations = ", ".join(scenario["source_cells"])
        if scenario["coverage_removed"]:
            low, high = scenario["remaining_dose_range"]
            add("dose_coverage", repr(dose), 4, f"Retain the bracketing dose at {dose:g}× unbound Cmax",
                f"Deleting {locations} narrows the measured range to {low:g}–{high:g}×. The original {describe_conclusion(primary)} lies outside that remaining range, which leaves {describe_conclusion(scenario)}.",
                "Keep the original dose evidence. If confirming this crossing is necessary, review the supporting measurements and consider an independent repeat with documented sampling.",
                source_rows, [scenario], ["dose_deletion"],
                "Lost dose coverage does not establish that the removed measurements are erroneous.")
        else:
            add("dose_dependence", repr(dose), 3, f"Inspect support at {dose:g}× unbound Cmax",
                f"Temporarily deleting {locations} changes {compound} from {describe_conclusion(primary)} to {describe_conclusion(scenario)}.",
                "Review these dose measurements and the sampling design. If the conclusion is needed, consider independently repeating this condition before interpreting the shift.",
                source_rows, [scenario], ["dose_deletion"],
                "Dose deletion tests dependence on available evidence; it does not identify a faulty dose.")

    model_names = {"raw_interpolation": "raw interpolation", "logistic": "the logistic comparator"}
    for scenario in changed:
        if scenario["kind"] != "model":
            continue
        name = model_names[scenario["model_name"]]
        failed = scenario["state"] == "fit_failed"
        add("comparator_limit" if failed else "model_disagreement", scenario["model_name"], 3,
            f"Inspect {name}",
            f"The primary fit gives {describe_conclusion(primary)}; {name} gives {describe_conclusion(scenario)}.",
            "Report this comparator as unavailable under its fitting requirements; inspect its numerical diagnostics." if failed else "Inspect both fitted curves and their assumptions. Retain the disagreement in the report rather than choosing a curve solely for its preferred result.",
            tested=[scenario], codes=["model", "logistic_diagnostics"] if failed else ["model"],
            interpretation="An unavailable comparator does not establish biological instability." if failed else "Curve disagreement alone does not identify a measurement error.")

    if primary["state"] in ["left_censored", "right_censored"]:
        low, high = primary["doses"][0], primary["doses"][-1]
        direction = "higher" if primary["state"] == "right_censored" else "lower"
        boundary = high if direction == "higher" else low
        boundary_rows = [row for row in records if row["dose_cmax_multiple"] == boundary]
        add("censored_result", "range", 6, f"Retain {compound}'s censored result",
            f"The primary fit gives {describe_conclusion(primary)} across {low:g}–{high:g}× unbound Cmax. No finite in-range crossing is supported.",
            f"If a finite crossing is required, resolve the identified evidence concerns first and assess {direction}-dose coverage with the laboratory, if experimentally appropriate. Otherwise retain the censored conclusion.",
            boundary_rows, codes=["threshold_bracket"])
    elif not changed:
        add("finite_scope", "result", 6, f"Report {compound}'s {primary['crossing']:.2f}× crossing",
            f"The primary fit gives {describe_conclusion(primary)}. None of the {len(scenarios)} tested scenarios materially changes that conclusion.",
            "Retain the source-linked estimate and the scope of the finite tests. Review documented sampling and control evidence before making broader experimental claims.",
            codes=["model", "reading_deletion", "dose_deletion"],
            interpretation="Agreement in these scenarios does not establish experimental validity or drug safety.")

    recommendations.sort(key=lambda item: (item["workflow_order"], item["id"]))
    return recommendations


def analyse_evidence(records):
    issues = audit_sources(records)
    if len(set(row["compound"] for row in records)) > 1:
        issues.append({"code": "mixed_compounds", "severity": "blocked", "source_record_id": "dataset", "message": "Analyse each compound separately; combining their readings would produce an invalid curve."})
    if any(issue["severity"] == "blocked" for issue in issues):
        return {"blocked": True, "issues": issues, "review": True, "models": [], "scenarios": [], "checklist": evidence_checklist(records, issues), "recommendations": build_recommendations(records, issues)}
    doses, samples = dose_samples(records)
    if len(doses) < 2:
        issues.append({"code": "insufficient_doses", "severity": "blocked", "source_record_id": "dataset", "message": "At least two observed positive dose conditions are required."})
        return {"blocked": True, "issues": issues, "review": True, "models": [], "scenarios": [], "checklist": evidence_checklist(records, issues), "recommendations": build_recommendations(records, issues)}
    models = []
    for name in MODEL_NAMES:
        models.append(fit_curve(doses, samples, name))
    primary = models[0]
    scenarios = []

    def add_scenario(kind, label, alternative, affected_records=None, probe_value=None):
        log_shift = None
        if primary["crossing"] is not None and alternative["crossing"] is not None:
            log_shift = float(abs(np.log10(primary["crossing"] / alternative["crossing"])))
        affected = affected_records or []
        affected_dose = float(affected[0]["dose_cmax_multiple"]) if affected else None
        if kind == "model":
            scenario_id = "model:" + alternative["model"]
        elif kind == "dose_deletion":
            scenario_id = "dose_deletion:" + repr(affected_dose)
        elif kind == "missing_probe":
            scenario_id = "missing_probe:" + affected[0]["source_record_id"] + ":" + repr(probe_value)
        else:
            scenario_id = "reading_deletion:" + affected[0]["source_record_id"]
        remaining_range = [alternative["doses"][0], alternative["doses"][-1]]
        coverage_removed = kind == "dose_deletion" and primary["crossing"] is not None and alternative["state"] in ["left_censored", "right_censored"] and not remaining_range[0] <= primary["crossing"] <= remaining_range[1]
        scenarios.append({"kind": kind, "label": label, "state": alternative["state"], "crossing": alternative["crossing"], "changed": conclusion_changed(primary, alternative), "log10_location_shift": log_shift, "original_state": primary["state"], "original_crossing": primary["crossing"], "source_record_ids": [row["source_record_id"] for row in affected], "source_cells": [row["source_sheet"] + "!" + row["source_cell"] for row in affected], "affected_values": [None if row["missing"] else row["value"] for row in affected], "interpretation": "Temporary deletion measures influence; no original observation is excluded or labelled erroneous." if kind in ["reading_deletion", "dose_deletion"] else "Alternative assumption or explicitly hypothetical missing value."})
        scenarios[-1].update({"scenario_id": scenario_id, "affected_dose": affected_dose, "model_name": alternative["model"], "probe_value": probe_value, "remaining_dose_range": remaining_range, "coverage_removed": bool(coverage_removed)})

    for model in models[1:]:
        if model["model"] != "constant":
            add_scenario("model", model["model"], model)
    for index, values in enumerate(samples):
        observed_records = [row for row in records if row["dose_cmax_multiple"] == doses[index] and not row["missing"]]
        if len(values) > 1:
            for reading_index in range(len(values)):
                reduced = [value.copy() for value in samples]
                reduced[index] = np.delete(values, reading_index)
                add_scenario("reading_deletion", f"dose={doses[index]:g};reading={reading_index + 1}", fit_curve(doses, reduced, "isotonic"), [observed_records[reading_index]])
        if len(doses) > 2:
            remaining_samples = [value for position, value in enumerate(samples) if position != index]
            affected = [row for row in records if row["dose_cmax_multiple"] == doses[index]]
            add_scenario("dose_deletion", f"dose={doses[index]:g}", fit_curve(np.delete(doses, index), remaining_samples, "isotonic"), affected)
    for row in records:
        if row["missing"]:
            for probe in MISSING_PROBES:
                hypothetical = []
                for source_row in records:
                    replacement = source_row.copy()
                    if replacement["source_record_id"] == row["source_record_id"]:
                        replacement["value"] = probe
                        replacement["missing"] = False
                    hypothetical.append(replacement)
                scenario_doses, scenario_samples = dose_samples(hypothetical)
                add_scenario("missing_probe", f"{row['source_record_id']}={probe:g}% (hypothetical)", fit_curve(scenario_doses, scenario_samples, "isotonic"), [row], probe)
    flags = []
    for kind in ["model", "reading_deletion", "dose_deletion", "missing_probe"]:
        if any(row["changed"] and row["kind"] == kind for row in scenarios):
            flags.append(kind)
    diagnostics = []
    for model in models:
        for code in model["diagnostics"]:
            diagnostics.append({"model": model["model"], "code": code})
    legacy_flags = flags.copy()
    if any(model["diagnostics"] for model in models if model["model"] == "logistic"):
        legacy_flags.append("logistic_fit_diagnostic")
    count_warning = any(row["missing"] for row in records) or min(len(values) for values in samples) < 2
    recommendations = build_recommendations(records, issues, primary, scenarios)
    next_steps = [item["title"] + ". " + item["reason"] + " " + item["action"] for item in recommendations]
    checklist = evidence_checklist(records, issues, primary, models, scenarios)
    unassessed_evidence = [item["code"] for item in checklist if item["status"] == "Not assessed" and item["layer"] == "evidence"]
    influential = [scenario for scenario in scenarios if scenario["kind"] == "reading_deletion" and scenario["changed"]]
    return {"blocked": False, "issues": issues, "doses": doses.tolist(), "means": [float(np.mean(values)) for values in samples], "counts": [len(values) for values in samples], "models": models, "primary": primary, "scenarios": scenarios, "flags": flags, "review": bool(flags), "diagnostics": diagnostics, "checklist": checklist, "influential_observations": influential, "legacy_flags": legacy_flags, "legacy_review": bool(legacy_flags), "count_warning": bool(count_warning), "source_warning": any(issue["severity"] in ["review", "blocked"] for issue in issues), "next_steps": next_steps, "recommendations": recommendations, "unassessed_evidence": unassessed_evidence}
