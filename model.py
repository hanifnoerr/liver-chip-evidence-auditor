"""A decreasing dose-response model with descriptive resampling diagnostics."""

import numpy as np

ALBUMIN_THRESHOLD = 50.0
BOOTSTRAP_DRAWS = 500
STABILITY_THRESHOLD = 0.95
MAX_SHAPE_ADJUSTMENT = 20.0


def fit_decreasing_response(means, counts):
    # Pool adjacent increasing blocks to solve weighted decreasing isotonic regression.
    blocks = []
    for index in range(len(means)):
        blocks.append([index, index, float(means[index]), float(counts[index])])
        while len(blocks) > 1 and blocks[-2][2] < blocks[-1][2]:
            left = blocks[-2]
            right = blocks[-1]
            total_weight = left[3] + right[3]
            pooled_mean = (left[2] * left[3] + right[2] * right[3]) / total_weight
            blocks[-2:] = [[left[0], right[1], pooled_mean, total_weight]]
    fitted = np.empty(len(means))
    for start, end, mean, weight in blocks:
        fitted[start:end + 1] = mean
    return fitted


def find_crossing(doses, fitted):
    if fitted[0] <= ALBUMIN_THRESHOLD:
        return None, "left_censored"
    for index in range(1, len(doses)):
        if fitted[index - 1] > ALBUMIN_THRESHOLD and fitted[index] <= ALBUMIN_THRESHOLD:
            fraction = (fitted[index - 1] - ALBUMIN_THRESHOLD) / (fitted[index - 1] - fitted[index])
            log_crossing = np.log10(doses[index - 1])
            log_crossing += fraction * (np.log10(doses[index]) - np.log10(doses[index - 1]))
            return float(10 ** log_crossing), "within_range"
    return None, "right_censored"


def bootstrap_responses(samples_by_dose, random_generator):
    counts = []
    for samples in samples_by_dose:
        counts.append(len(samples))
    curves = []
    for draw in range(BOOTSTRAP_DRAWS):
        sampled_means = []
        for samples in samples_by_dose:
            sampled_values = random_generator.choice(samples, size=len(samples), replace=True)
            sampled_means.append(float(np.mean(sampled_values)))
        curves.append(fit_decreasing_response(sampled_means, counts))
    return np.array(curves)


def analyse_albumin(doses, samples_by_dose, random_generator):
    means = []
    counts = []
    for samples in samples_by_dose:
        means.append(float(np.mean(samples)))
        counts.append(len(samples))
    means = np.array(means)
    fitted = fit_decreasing_response(means, counts)
    crossing, censoring = find_crossing(doses, fitted)
    bootstrap_curves = bootstrap_responses(samples_by_dose, random_generator)
    bootstrap_crossings = []
    censor_counts = {"left_censored": 0, "right_censored": 0, "within_range": 0}
    for curve in bootstrap_curves:
        sampled_crossing, sampled_censoring = find_crossing(doses, curve)
        censor_counts[sampled_censoring] += 1
        if sampled_crossing is not None:
            bootstrap_crossings.append(sampled_crossing)
    crossing_fraction = len(bootstrap_crossings) / BOOTSTRAP_DRAWS
    weighted_error = np.average((means - fitted) ** 2, weights=counts)
    shape_adjustment = float(np.sqrt(weighted_error))
    reasons = []
    if min(counts) < 2:
        reasons.append("At least one dose has fewer than two observed albumin values.")
    if shape_adjustment > MAX_SHAPE_ADJUSTMENT:
        reasons.append("The decreasing model changes dose means by more than 20 percentage points RMS.")
    if censoring == "within_range" and crossing_fraction < STABILITY_THRESHOLD:
        reasons.append("The 50% crossing disappears in more than 5% of resamples.")
    if censoring == "right_censored":
        decision = "crossing_not_observed"
    elif censoring == "left_censored":
        decision = "crossing_below_tested_range"
    elif reasons:
        decision = "crossing_requires_review"
    else:
        decision = "crossing_stable_in_resampling"
    crossing_range = None
    if bootstrap_crossings:
        crossing_range = np.quantile(bootstrap_crossings, [0.025, 0.975]).tolist()
    return {
        "doses": np.array(doses).tolist(),
        "observed_means": means.tolist(),
        "observed_counts": counts,
        "fitted_albumin": fitted.tolist(),
        "response_resampling_range": np.quantile(bootstrap_curves, [0.025, 0.975], axis=0).tolist(),
        "albumin_50_crossing": crossing,
        "censoring": censoring,
        "crossing_resampling_fraction": crossing_fraction,
        "resampling_censor_counts": censor_counts,
        "crossing_resampling_range_conditional_on_crossing": crossing_range,
        "shape_adjustment_rms_pp": shape_adjustment,
        "decision": decision,
        "review_reasons": reasons,
    }


def evaluate_held_doses(doses, samples_by_dose, random_generator):
    # Hold all measurements at one dose out together; evaluate only interpolation.
    rows = []
    doses = np.array(doses)
    log_doses = np.log10(doses)
    for held_index in range(1, len(doses) - 1):
        training_doses = np.delete(doses, held_index)
        training_log_doses = np.log10(training_doses)
        training_samples = []
        means = []
        counts = []
        for index, samples in enumerate(samples_by_dose):
            if index != held_index:
                training_samples.append(samples)
                means.append(float(np.mean(samples)))
                counts.append(len(samples))
        fitted = fit_decreasing_response(means, counts)
        prediction = float(np.interp(log_doses[held_index], training_log_doses, fitted))
        baseline = float(np.interp(log_doses[held_index], training_log_doses, means))
        constant_baseline = float(np.average(means, weights=counts))
        observed = float(np.mean(samples_by_dose[held_index]))
        curves = bootstrap_responses(training_samples, random_generator)
        predictions = []
        for curve in curves:
            predictions.append(float(np.interp(log_doses[held_index], training_log_doses, curve)))
        lower, upper = np.quantile(predictions, [0.025, 0.975])
        rows.append({
            "dose_cmax_multiple": float(doses[held_index]),
            "training_doses": training_doses.tolist(),
            "observed_albumin_mean": observed,
            "monotone_prediction": prediction,
            "raw_interpolation_prediction": baseline,
            "constant_prediction": constant_baseline,
            "resampling_lower": float(lower),
            "resampling_upper": float(upper),
            "resampling_range_contains_mean": bool(lower <= observed <= upper),
        })
    return rows
