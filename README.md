# Liver-Chip Evidence Auditor: Albumin Response Review and Follow-up Planning

Combine dose-response modelling and a compact local language model to inspect influential liver-chip albumin readings, choose feasible follow-ups, and record the outcome.

The statistical auditor links sensitive conclusions to source workbook cells. The optional 135M model selects an action from the audit, researcher request and available resources. Python supplies the measurements and checks eligibility, with a rules fallback for ineligible proposals. The exported review preserves the evidence, selected action and recorded findings.

## Start the app

Extract the code package and run:

```powershell
conda env create -f environment.yml
conda activate ai4s-liver-auditor
python demo.py
```

Open the address printed by `demo.py`.

1. Select a compound in Review, or import an albumin CSV. Inspect the conclusion, evidence checks and affected readings.
2. Open Next action, set your goal and resources, then select “Find a next action.”
3. Use “Record what happened” to document inspection or upload a complete compatible revised CSV. Notes preserve the computed result; revised measurements produce a new audit for comparison.
4. Export the record before closing the browser tab; plans use session storage.

Validation contains evaluation results. Data & sources contains provenance and licences. Guide contains CSV requirements and setup instructions. To view saved results, open `auditor_demo.html` and keep its accompanying HTML, CSS and JavaScript files together.

## CSV input

Follow [data/measurements.csv](data/measurements.csv). Use day-three `albumin_percent`, positive doses in `x_unbound_cmax` and responses in `percent_source_normalised`. Give each original observation a unique source-record ID. Leave unknown chip, sample, run and donor IDs empty; source IDs identify readings, not independent chips. Incompatible units, duplicated IDs and derived observations block fitting.

## Try the experimental model

Extract `liver_chip_slm_result.zip` into the same project root, then run:

```powershell
conda env create -f small_model/environment.yml
conda activate ai4s-liver-slm
python demo.py --model small_model/checkpoints/smollm2-135m-policy --threads 4
```

Select “Small language model · experimental” in Next action. [Model instructions](small_model/README.md) cover training and deployment.

## Reproduce the analysis

In the core environment, run:

```powershell
python run_auditor.py
python check_auditor.py
python check_followthrough.py
python -m small_model.check_planner
```

Results are written to `results/auditor/`. Source workbooks are downloaded if absent. The [protocol](evaluation_protocol.md) records the original evaluation and warning revision.

## Evaluation

The public subset contains six compounds, 35 dose conditions and 70 albumin readings, including two missing values. Across 23 correlated within-compound holdouts, MAE was 16.36 percentage points for isotonic regression, 16.69 for raw interpolation and 20.07 for logistic fitting.

The revised warning detected one retrospective evidence-restoration change with 12 additional warnings, compared with 20 for the original rule. In 96 fresh-seed simulations it detected ten errors with 52 false warnings; an earlier seed had two missed errors. The warnings support manual evidence inspection. Improving their precision is the next numerical development priority.

The adapted 135M model matched 337/364 authored policy targets before checks and 361/364 after checks. Rules matched 364/364 and provide the default baseline. The scope guard corrected all 24 tested unsupported-request errors. Per-class results identify the next training priorities and are documented in the technical report. CPU action-code scoring took a median of 1.33 seconds on the tested PC; device-specific edge benchmarks and quantisation are planned deployment steps.

The current scope is day-three albumin evidence review. Independent laboratory evaluation will require chip/run identities, raw controls and new compounds. Expert-reviewed action labels and a reader study will test the planner's practical contribution. Full results and the validation plan are in the [technical report](https://github.com/hanifnoerr/liver-chip-evidence-auditor/releases/download/v1.0.0/technical_report.pdf).

## Framework and supporting files

[Numerical analysis](framework.svg) · [Action selection](action_framework.svg) · [Outcome recording](followthrough_framework.svg). [framework_notes.md](framework_notes.md) maps inputs, outputs and functions. Run `python build_framework.py` to regenerate the figures.

[Rendered contrast checks](results/auditor/colour_contrast_checks.json) record tested interface states; they are not a full accessibility audit. Colour references: [USWDS](https://designsystem.digital.gov/design-tokens/color/system-tokens/) and [W3C](https://www.w3.org/WAI/WCAG22/Understanding/contrast-enhanced.html).

The original resampling pilot is preserved in `method.md`; run `python run_experiment.py` and `python check_model.py` to reproduce it.

## Attribution

[Ewart et al., Communications Medicine, 2022](https://doi.org/10.1038/s43856-022-00209-1), Supplementary Data 1 and 8, CC BY 4.0. Original workbooks and source-cell references are preserved. Code: [MIT](LICENSE). Third-party attribution: [NOTICE.md](NOTICE.md).
