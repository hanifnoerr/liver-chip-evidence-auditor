# Public Liver-Chip data

This document describes the core data used by the pilot and evidence auditor. The portable submission bundle includes **Supplementary Data 1 and 8**. The full working checkout also contains other acquired candidate sources; they are excluded from the core release and its model. Their availability does not validate the deferred paired ALT project.

Retrieved 1 October 2026 from the publisher's supplements to Ewart et al., *Performance assessment and economic analysis of a human Liver-Chip for predictive toxicology*, Communications Medicine 2,154 (2022), [DOI 10.1038/s43856-022-00209-1](https://www.nature.com/articles/s43856-022-00209-1).

- [Supplementary Data 8](https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs43856-022-00209-1/MediaObjects/43856_2022_209_MOESM8_ESM.xlsx) supplies the response measurements used in this prototype.
- [Supplementary Data 1](https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs43856-022-00209-1/MediaObjects/43856_2022_209_MOESM1_ESM.xlsx) supplies dosing/reference information. It is retained for inspection, not joined into the fitted model.
- [Supplement description](https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs43856-022-00209-1/MediaObjects/43856_2022_209_MOESM11_ESM.pdf) identifies the six-drug response subset. Its figure numbers differ from the current article; worksheet headers are the schema used here.

The article states a [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) licence, subject to credited third-party exceptions. We retain attribution to the authors and publisher. The raw files are unmodified; `measurements.csv` is a reshaped derivative with missing-value strings converted to empty values. No patient records or raw microscopy are included.

## Inspected structure

The `ALBUMIN`, `ALT`, and `Morphology` worksheets each contain 70 rows and three columns: compound, `Concentration_Day3`, and endpoint value. There are six drugs and 35 unique drug-dose conditions. Each condition has two rows in each endpoint sheet. Six endpoint values are missing: two albumin values for pioglitazone and two each of ALT and morphology for the highest troglitazone dose. There are 204 observed endpoint values in 210 source rows.

`Concentration_Day3` is interpreted as the dose multiple plotted for the response comparisons, using the article's unbound human Cmax convention and cross-checking the dose grid against Supplementary Data 1. It is not a concentration in micromolar. Troglitazone's non-integer multiples are retained; Supplementary Data 1 explicitly describes a dosing calculation error. We do not round them to nominal values or recompute total/free exposure.

Albumin is in the supplied normalised percentage scale. The model's fixed threshold is 50 on that scale; we do not renormalise to the lowest tested dose. Morphology scores retain their supplied 0–4 scale and fractional values. ALT retains source units; the workbook does not state the unit or provide the vehicle reference needed for a diagnostic threshold.

## What cannot be reconstructed

The response sheets do not provide chip IDs, donor IDs, cycle IDs, longitudinal correspondence, raw vehicle controls, or well identifiers. Two rows at a dose are treated as available repeated endpoint measurements. Their biological independence is not established. Endpoint rows are aggregated within compound and dose separately; matching row order is not used to fabricate paired multivariate chip observations. Source row numbers preserve provenance and are not surrogate biological IDs.

This data permits a within-drug dose-interpolation pilot and descriptive crossing analysis. It does not permit early-to-late response prediction, donor-held-out evaluation, cross-laboratory validation, or reproduction of the paper's complete clinical DILI sensitivity/specificity analysis.

The [January 2023 correction](https://www.nature.com/articles/s43856-023-00235-7) changes the spheroid specificity in Table 5 to 67%. The [February 2023 correction](https://www.nature.com/articles/s43856-023-00249-1) replaces duplicated Table 3 data. Both correction notices were checked; neither specifies a change to the response workbook used here.
