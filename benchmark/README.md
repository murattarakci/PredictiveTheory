# The CSP–CFP benchmark

These scripts rebuild the 2,208 between-firm specifications that Berchicci and King (2022, *Strategic Management Journal*) derived from six studies of corporate social performance (CSP) and financial performance. They score every specification on firms held out from estimation. The results are reported in the technical appendix of our *Organization Science* Stage 1 proposal.

## Data

The scripts need the Compustat and KLD files that Berchicci and King built. These are licensed and **are not in this repository**. Place the three lockbox splits in `benchmark/Data/`:

- `repo_1_train.csv` and `repo_1_test.csv` (training and test sets from the lockbox)
- `repo_5_validation.csv` (validation set from the same split)

The split is 60-20-20 by firm (`gvkey`). No firm appears in more than one set.

## Run order

From the `benchmark/` folder:

```bash
Rscript --vanilla rerun_v2_corrected.R
Rscript --vanilla results_v2/clustered_se_v2.R
Rscript --vanilla results_v2/final_v2.R
Rscript --vanilla results_v2/best_model_table_v2.R
python3 results_v2/figures_v2.py results_v2 results_v2
```

| Script | What it does |
|---|---|
| `modelCombinations.R` | Builds the specification grid |
| `rerun_v2_corrected.R` | Fits every specification and scores it on test and validation firms |
| `results_v2/clustered_se_v2.R` | Adds standard errors clustered by firm |
| `results_v2/final_v2.R` | Drops the 192 duplicate specifications, prints the summary, and bootstraps the 50 best |
| `results_v2/best_model_table_v2.R` | Produces the table for the specification ranked first on the test set |
| `results_v2/figures_v2.py` | Draws the two appendix figures |

The grid script builds 2,400 specifications. 192 of them are quadratic forms of a binary CSP indicator, whose square equals itself, so they duplicate linear specifications. `final_v2.R` removes them, leaving 2,208.

## Results

The scripts write their output to `results_v2/`. The printed summary (`final_summary_v2.txt`), the table for the specification ranked first on the test set (`best_model_table_v2.txt`), and the two figures are included here. The specification-level result tables are derived from licensed data and stay with the authors; they are available on request.

## Corrections to the first run (April 2026)

The header of `rerun_v2_corrected.R` documents three corrections:

1. **Lagged outcome.** The lag now uses the firm's annual value from the previous year. The first run lagged the firm average, so the outcome was mostly used to predict itself.
2. **Cross-validation folds.** These now fit on four folds and score on the fifth. The first run had them reversed.
3. **Industry and year effects.** Specifications with these effects now receive scores. In the first run they could not be scored.
