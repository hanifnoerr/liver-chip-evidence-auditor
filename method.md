# Reliability of albumin response estimates in a sparse Liver-Chip assay

**Auditor revision, 4 October 2026:** the approved evidence checklist, source-linked influence report and paired computational A/B comparison are implemented. Standalone numerical diagnostics no longer force review; original measurements remain in fitting. The current method and results are in [the technical report](https://github.com/hanifnoerr/liver-chip-evidence-auditor/releases/download/v1.0.0/technical_report.pdf). The modelling pilot described below remains unchanged.

**Status, 2 October 2026:** this document records the preserved modelling pilot. The **Liver-Chip Evidence Auditor**, category **Tool & Platform**, is now implemented and evaluated in `auditor.py` and `run_auditor.py`. Its actual results and limitations are in [the technical report](https://github.com/hanifnoerr/liver-chip-evidence-auditor/releases/download/v1.0.0/technical_report.pdf); the full output is `results/auditor/results.json`. The broad review rule has many false warnings and is not a validated automatic decision rule.

## Intended decision and current contribution

A scientist has measured a drug at several doses and needs to know whether the observed albumin response supports a functional effect estimate. The prototype fits a decreasing dose-response curve and reports a finite 50% crossing only when it lies inside the measured dose range. It records missing observations, resampling instability, and departures from the decreasing-response assumption. These outputs help identify measurements to review; they do not determine whether a drug is clinically safe.

The current algorithm is a transparent statistical learning baseline. Isotonic regression and percentile resampling are established methods. Their combination here is an adaptation to the Liver-Chip endpoint, not an established novel method. The research contribution still needs to be demonstrated through improved uncertainty calibration and useful review decisions under independent experimental variation.

## Inputs and fitted quantities

For each drug, let d_j be a positive dose multiple, y_jk an observed normalised albumin percentage, and n_j the number of observed values at dose j. Missing values remain missing. The source workbook supplies day-three endpoint values, with at most two observations per dose and no chip or donor identifiers.

We calculate the mean m_j at each dose. We learn response values z_j by solving

$$\min_{z_1,\ldots,z_J}\sum_{j=1}^{J} n_j(m_j-z_j)^2,\qquad z_1\ge z_2\ge\cdots\ge z_J.$$

The pool-adjacent-violators algorithm merges neighbouring blocks whose weighted means violate the decreasing constraint. No shared predictor across drugs is trained. Between tested doses we interpolate z linearly in log10(d). This is an assumption about the response shape, not evidence that every liver injury mechanism is monotone.

The threshold is fixed at 50% on the supplied albumin scale. If the fitted response is already at or below 50 at the lowest dose, the crossing is left censored. If it remains above 50 at the highest dose, it is right censored. We do not extrapolate a finite crossing in either case. For a bracketed crossing between adjacent points, we interpolate in log dose. This operational crossing is not a fitted four-parameter-logistic IC50 or a clinical margin of safety.

## Resampling and review rules

We resample the available endpoint measurements separately within each dose, with replacement, and refit the curve 500 times. We report the fraction of curves with finite crossings, the 2.5th and 97.5th percentiles of fitted responses, and crossing percentiles conditional on a finite crossing. Conditional crossing ranges exclude censored draws, so the crossing fraction and censor counts are reported alongside them.

The analysis requests review of a finite point crossing when fewer than two albumin observations exist at any dose, when fewer than 95% of resampled curves have finite crossings, or when the weighted root mean square adjustment from raw dose means to the constrained fit exceeds 20 percentage points. These are uncalibrated prototype rules. They do not assign a calibrated probability of failure. Censored curves keep their censoring status, with review reasons recorded separately.

Sparse resampling cannot recover unobserved donor variability, shared-control error, between-run variation, or missing observations. A single observed value resamples to itself and can produce a zero-width range. The missingness rule prevents such an artefact from earning the finite-crossing stability status. Even the two-observation case can underestimate uncertainty, as the held-dose experiment demonstrates.

ALT and morphology are summarised independently within drug and dose. They provide visible supporting observations. We do not fuse them into a trained multivariate response, assign diagnostic thresholds, or pair their rows with albumin using an assumed chip identity.

## Actual evaluation

For each drug, every interior dose is held out in turn, including all its endpoint measurements. We fit each predictor to that drug's remaining albumin doses and predict the mean at the held dose. Resampling also uses only those training doses. The two boundary doses are excluded because this experiment evaluates interpolation. There are 23 held-dose conditions across six drugs. Dose conditions from one drug are dependent, so the 23 folds are not 23 independent drug experiments.

The baselines are interpolation of the unmodified observed dose means in log dose and a constant mean weighted by observation count. All methods use the same held conditions. MAE and RMSE are measured in albumin percentage points, averaged over conditions. Source preparation, diagnostics, fitting, and evaluation ran on the downloaded public data; this is not a simulated-data result.

| Method | MAE | RMSE |
|---|---:|---:|
| Decreasing isotonic regression | 16.3633 | 22.1591 |
| Raw mean interpolation | 16.6914 | 22.8287 |
| Constant mean | 20.8878 | 24.2853 |

The constrained fit reduces MAE by 0.3281 percentage points relative to raw interpolation. This pilot does not establish statistical significance or a general performance advantage. The resampling response ranges contain 8 of the 23 held means, giving 34.8% descriptive coverage. The percentile endpoints therefore cannot be advertised as calibrated 95% prediction intervals. The response means at unmeasured doses introduce interpolation error that resampling the measured values alone does not capture.

| Drug | Finite fitted crossing, × Cmax | Resamples with crossing | Current evidence status |
|---|---:|---:|---|
| Clozapine | None; right censored | 26.0% | Crossing not observed in point fit |
| Levofloxacin | None; right censored | 0.0% | Crossing not observed in tested range |
| Olanzapine | None; right censored | 0.0% | Crossing not observed in tested range |
| Pioglitazone | 292.51 | 73.8% | Review; two missing albumin values and unstable crossing |
| Troglitazone | 162.38 | 100.0% | Crossing stable in available-data resampling |
| Trovafloxacin | 89.99 | 100.0% | Crossing stable in available-data resampling |

Troglitazone also has the largest held-dose MAE, 27.94 percentage points. A stable crossing under sparse resampling can coexist with poor interpolation. We therefore preserve this distinction in the demo and do not translate the stability status into a general reliability score.

## Framework verification

The original pilot framework is now preserved as [pilot_framework.svg](results/pilot_framework.svg). The root `framework.svg` depicts the implemented auditor; the map below remains a record of the pilot computation.

The editable figure shows per-drug curve fitting and diagnostics, with a separate held-dose evaluation panel. It contains no image encoder, donor predictor, neural network, clinical classifier, or learned uncertainty component because none is implemented.

| Figure operation | Inputs → outputs | Implementation |
|---|---|---|
| Read source rows | Workbook cells → long endpoint records and missing flags | `prepare_data.py`, `prepare_data` |
| Learn decreasing response | Dose means m and counts n → fitted z | `model.py`, `fit_decreasing_response` |
| Find 50% crossing | Dose d and z → finite crossing or censoring | `model.py`, `find_crossing` |
| Resample within dose | Observed values → 500 fitted curves | `model.py`, `bootstrap_responses` |
| Assess support | Crossing draws, counts, shape adjustment → review reasons/status | `model.py`, `analyse_albumin` |
| Hold dose out | Remaining doses → held prediction and response range | `model.py`, `evaluate_held_doses` |
| Report evidence | Independently summarised endpoints and model outputs → local demo | `run_experiment.py`, `run_experiment` |

Figure caption. The implemented Liver-Chip pilot learns a decreasing albumin response from the available measurements for each drug. Fixed diagnostic rules distinguish finite crossing support from censoring and missing evidence. The close-up shows descriptive resampling and review criteria. The evaluation panel excludes all measurements at each held interior dose. Blue boxes denote fitted response values; ochre boxes denote fixed, uncalibrated rules.

## Targeted research next steps

The specialised question is whether a method can distinguish a well-supported albumin response from an underdetermined response under sparse replication, donor shifts, and limited dose coverage. The six-drug workbook establishes a runnable assay-specific starting point and exposes uncertainty failure. It does not supply the independent units needed to answer the full question.

1. Obtain public raw chip-level albumin and vehicle controls with donor, cycle, dose, and day identifiers. Pair endpoints only with verified chip IDs. Preserve unbound exposure and control normalisation provenance. Restrict the initial endpoint to albumin rather than expanding into many organs or disease outcomes.
2. Compare this pilot with a bounded four-parameter-logistic fit and a hierarchical donor/run dose-response model. Use grouped chip resampling where independence is supported. Fit response parameters and calibrate review thresholds using training/validation experiments, then hold out complete donors or drugs for the declared task.
3. Calibrate response prediction intervals on independent experimental groups. Evaluate coverage, width, and censoring-aware crossing output. Six drugs do not support a useful finite distribution-free 95% conformal threshold using five calibration drugs; the conformal rank exceeds the available calibration scores. Report this sample-size limitation rather than relabelling a percentile range as conformal.
4. Test review decisions using risk versus retained coverage, including full coverage and simple missingness/residual baselines. Test whether recommended extra measurements reduce crossing ambiguity relative to random extra-dose selection, using a separate acquisition simulation with genuinely hidden measurements. This acquisition experiment is not yet implemented.

Biological validation needs a collaborator to interpret endpoint-specific failure. Transport changes, protein binding, loss of viable hepatocyte function, and true drug response can affect the assay. The present workbook cannot identify these causes. The model should report ambiguity rather than attribute it to a named mechanism.

## Literature and differentiation

[Ewart et al. (2022)](https://www.nature.com/articles/s43856-022-00209-1) provide the actual Liver-Chip response source and demonstrate why donor coverage and exposure conventions matter. We adapt their albumin endpoint, without attempting to reproduce their full clinical classification from this subset.

[Baudy et al., Lab on a Chip 20,215–225 (2020)](https://pubs.rsc.org/en/content/articlehtml/2020/lc/c9lc00768g?page=search) specify liver-MPS benchmarking stages and a safety test set. The publisher abstract was accessible; full-text retrieval was blocked. We use it to ground the need for a defined context of use, not to claim compliance with unread criteria.

[Pamies et al., Stem Cell Reports 19,604–617 (2024)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11103889/) distinguish quality criteria across cell, device, experiment, and data handling. Their recommendation to specify acceptance criteria motivates explicit missing-evidence flags. Our response diagnostics do not establish that the physical chip meets those criteria.

A [2026 liver-chip digital-twin study](https://www.sciencedirect.com/science/article/abs/pii/S1385894726045079) describes a microfluidics/PBPK-PD model with Bayesian and learned discrepancy uncertainty for GST-alpha. The indexed publisher abstract was inspected; the full article was inaccessible. It is close prior work, so generic uncertainty-aware liver-chip prediction is not a defensible novelty claim. Our proposed differentiation is censoring-aware support for sparse albumin dose-response estimates, tested across independent experimental units. That differentiation remains a research hypothesis.

## Submission readiness

The pilot was originally positioned in Model & Algorithm. The current planned submission category is **Tool & Platform**, with this model serving as one component of an evidence auditor. The existing HTML still demonstrates the pilot's computations, not the complete planned tool.

Pilot rubric self-assessment is approximately **52/100**: impact 23/30, innovation 10/30, validation 5/20, reproducibility 9/10, presentation 5/10. These are planning judgements, not predictions of a judge's marks. Real OoC data and executable code strengthen fit; sparse validation, established methods, and absent calibrated uncertainty limit the pilot. The current completed-tool planning estimate is **62/100**, conditional on evidence and deliverables still missing; its breakdown is in [submission_plan.md](submission_plan.md).

Local CPU operation is sufficient for this pilot. The measured analysis stage took about one second on this Windows host, excluding download, workbook preparation, and output export. No memory, power, target-device latency, or edge-device test has been performed. Edge deployment should follow a demonstrated offline instrument workflow rather than becoming the main research claim.
