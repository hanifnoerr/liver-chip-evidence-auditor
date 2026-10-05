# Frozen evaluation protocol

Frozen on 2 October 2026, before implementing the auditor comparisons. The Ewart workbook has already been inspected; real-data evaluation is exploratory, not blinded.

The primary endpoint is source-normalised day-three albumin. The operational threshold is 50%. Doses are multiples of unbound Cmax. Six compounds form three published comparison pairs. Experimental chip/donor/run identities are unknown.

## Models and conclusion

Compare weighted non-increasing isotonic regression, raw dose-mean interpolation, a constant training mean, and a four-parameter decreasing logistic curve. Interpolation is linear in log10 dose. Fits use dose means weighted by observed counts. Logistic lower level and amplitude are non-negative, slope is between 0.1 and 10, and log midpoint lies within two decades of the training dose range. Fit failure, active parameter bounds and rank deficiency are reported. A fit's midpoint is not automatically its 50% normalised-response crossing.

A crossing conclusion comprises left censoring, right censoring or a crossing within the tested range. A response at or below 50% at the lowest tested dose is left-censored under the implementation's boundary convention. Otherwise, report the first downward crossing; right censoring means no such crossing was reached within the tested range and does not assert an eventual crossing. A material location change is a change greater than a factor of two. This is a fixed operational review rule, not a clinical margin. Report continuous changes as well. Raw interpolation can be non-monotonic; flag multiple downward crossings or transitions across 50% in both directions.

Implementation correction, 5 October 2026: search interior downward crossings before assigning right censoring to a raw curve whose final response exceeds 50%. Add a diagnostic for a downward crossing followed by a return above 50%. Thresholds and sensitivity scenarios remain unchanged.

## Auditor scenarios

The primary fit is isotonic. Refit it after deleting each observed reading and after deleting each dose, including boundaries. Compare it with raw interpolation and a fitted logistic curve. Do not include the constant baseline in the model-agreement warning. Hypothetical missing albumin values are 0, 50, 100, 150 and 200 percent, one missing record at a time. These values are sensitivity probes, not imputations or biological bounds. The missingness remains unresolved beyond this finite scenario set.

Report model disagreement, observation/dose deletion sensitivity and missing-value sensitivity separately. The combined review decision is their union, plus failed/weakly identified logistic comparison. Source faults are a separate output. Missing experimental identity limits pairing and group validation but does not force every endpoint conclusion into review.

## Real-data evaluation

Use all 23 interior dose conditions. Remove all readings at a held dose before prediction and warning computation. Score the held observed mean in percentage points using MAE and RMSE; report every model's eligible count and failures. Do not extrapolate in this prediction test.

After fitting and warning, restore the withheld dose and compare the isotonic conclusion to its full-data counterpart. A changed state or greater-than-twofold crossing-location change is the reference event. The reference is evidence restoration, not biological ground truth. Report precision, recall, false warnings, missed changes, retained fraction and held-dose error among retained conditions. Undefined ratios remain null.

Compare no warning, training missingness or fewer-than-two-readings warning, source-only warning, sensitivity-only warning and their combination. Report per-compound results. The 23 folds are correlated within six compounds; do not treat them as 23 independent drug studies or make significance claims.

## Synthetic evaluation

Use independent seeds 20261001 (development) and 20261002 (evaluation), 96 experiments per partition. Generate six log-spaced doses, two readings per dose, and explicit distinct synthetic chips within each simulated run. Cycle through Hill and piecewise response shapes and eight scenarios: clean, random missingness, response-dependent missingness, truncated dose range, singleton counts, influential observation, non-monotonic response and run shift. There is no longitudinal or multi-endpoint pairing claim. The latent response including the simulated run shift determines the reference crossing.

Analyse each synthetic experiment independently. Do not train on the evaluation experiments or change thresholds using their results. Compare full, source-only, sensitivity-only and count-warning outputs against the known crossing state/material location error. Separate controlled metadata-fault fixtures from response simulation, include a clean fixture, and report only those known fault cases. Simulation cannot establish human injury prediction.

## Reproduction and changes

Use a dedicated CPU Conda environment and pinned dependencies. Preserve the original pilot output. Save scenario rows, source issues, model predictions, confusion counts, undefined quantities, generator assumptions and measured runtime. Any deviation from this protocol must be documented before presenting its result; negative results are retained.

## Revision frozen on 4 October 2026

The 2 October real-data and synthetic results have already been inspected. Preserve their saved output as `results/auditor/legacy_results_20261002.json`. Comparisons on those cases are retrospective. The revision changes evidence reporting and warning composition; fitted curves, the 50% threshold, the factor-of-two rule, scenarios and generator remain unchanged.

Separate hard input failures, missing evidence, material sensitivity changes and numerical fit diagnostics. The revised sensitivity warning is the union of material scenario changes. The revised combined warning adds missing-source warnings. Logistic parameter bounds and weak identification remain visible diagnostics but no longer trigger review alone. A failed logistic comparison still counts as a material model scenario. Preserve the previous diagnostic-inclusive rule as a legacy comparator. Do not change these rules after observing the new results.

For a paired computational A/B comparison, A uses the same fitted isotonic conclusion without warnings; B uses the revised combined warning and evidence report. Include the legacy rule to expose the effect of demoting standalone diagnostics. Compare missed reference changes, warnings without a reference change, retained fraction and held-dose error among retained cases. The A/B arms share predictions, so an improvement in raw prediction accuracy is not expected. This is not a human reader study or a biological treatment-control experiment.

After implementing the frozen revision, generate 96 additional experiments with seed 20261004, partition `revision_evaluation`. Apply A, legacy and revised rules to identical cases before accessing latent truth for scoring. This seed has not been inspected when the revision is specified. It is fresh simulated evaluation within the existing generator, not independent experimental data or a new response family. Report all results, including losses in recall and false warnings. Retain the earlier two partitions with explicit retrospective labels.

Checklist statuses are Pass, Fail and Not assessed. A pass concerns the named computational check only. Missing raw vehicle/reference controls, assay calibration, device QC or documented experimental independence remain Not assessed. A failed threshold-bracketing check prevents a finite in-range estimate; it does not invalidate a correctly censored result. Do not combine checklist statuses into a safety score.

Attach source-record IDs, source cells and removed values to observation-deletion scenarios. Keep original readings in fitting/export; temporary deletion measures influence and does not establish an erroneous outlier. Highlight observations whose deletion changes the operational conclusion. Exclusion requires separately documented technical evidence; this release does not automatically exclude observations. Export all paired decisions and checklist items, not just favourable cases.

Implementation clarification: reading-deletion checks require another observed reading at that dose. Dose-deletion checks require at least three observed doses before deletion. Singleton-dose influence is covered by those eligible dose-deletion scenarios. These eligibility conditions are unchanged from the original implementation.
