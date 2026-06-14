# Reproducing the paper's reported numbers

This document lets a reviewer regenerate every quantitative value reported in the
main text from the bundled data and code. All estimators and the ensemble-weight
optimization are deterministic (fixed multi-start + L-BFGS-B, no random seed), so
the same input always yields the same output.

## Environment

```bash
python3 -m pip install -r requirements.txt   # numpy, scipy, Pillow, ...
export MPLBACKEND=Agg                          # headless (no display needed)
```

## Data baseline (bundled, checksum-pinned)

| file | role | md5 |
|------|------|-----|
| `dbfiles/alldata.db`     | 33-image analysis pool (descriptors + ROIs) | `8c2aacc4b864597260207b7ebeeeec7b` |
| `dbfiles/raman.raman.db` | 20 image–Raman pairs                         | `350ee4d15ec6006a95f4c22c6eb99d92` |
| `dbfiles/pkw_1.db`       | 20-image Raman-linked subset                 | `67bed900e0708a76906d5ffed2b98a05` |
| `dataset/images/`        | 33 sample photographs (PNG)                  | see `dbfiles/CHECKSUMS.md5` |

Verify integrity: `md5sum -c dbfiles/CHECKSUMS.md5`

## One command → the main-text aging-day numbers

```bash
python3 tools/reproduce_paper_4method.py
```

Expected output (matches the paper exactly):

```
  [산화 3조건] (Native35 + Native70 + PMMA, n=21)
    uniform              RMSE =  6.32 d   (paper 6.32)
    global-weight  strict LOO =  3.30 d   (paper 3.30  ← headline)
    condition-specific    LOO =  4.17 d   (paper 4.17)
  [Al2O3 단독] (n=12, outside operating range)
    global-weight  strict LOO = 10.04 d   (paper ~10)
  [kNN per-cond solo RMSE]
    NativeHfS2-35%RH  kNN = 3.12 d   (paper 3.12)
    NativeHfS2-70%RH  kNN = 3.56 d   (paper 3.56)
```

## Raman calibration metrics

```bash
python3 tools/reproduce_raman_calibration.py
```

Reproduces the pseudo-Raman A₁g calibration (4-OLS R²-weighted ensemble,
leave-one-out over the 20 image–Raman pairs):

```
  R²    = 0.56   (paper 0.56)
  RMSE  = 0.21   (paper 0.21)
  r     = 0.77   (paper 0.77)
  MAE   = 0.165  (paper 0.165)
```

## Supporting analyses

```bash
python3 tools/loo_no_kinetic.py     # 5-method vs 4-method (kinetic removal) — why 4 estimators
python3 tools/nested_loo_eval.py    # in-sample vs nested-LOO (leakage check)
```

`loo_no_kinetic.py` reproduces the 4-method table: uniform 7.15, global in-sample 6.34 /
nested-LOO 6.60, condition-specific in-sample 5.19 / nested-LOO 6.30.

## Paper number → command mapping

| Paper value | Source |
|-------------|--------|
| 3.30 d (headline, oxidizing global LOO) | `reproduce_paper_4method.py` |
| 6.32 d (oxidizing uniform)              | `reproduce_paper_4method.py` |
| 4.17 d (oxidizing condition-specific)   | `reproduce_paper_4method.py` |
| ~10 d (Al2O3, all schemes)              | `reproduce_paper_4method.py` |
| kNN 3.12 / 3.56 d (per-condition)       | `reproduce_paper_4method.py` |
| global weights ≈ kNN 0.85 / spatial 0.15 | `optimize_weights_headless.py --pool dbfiles/alldata.db --targets dataset/images` |
| Raman R²=0.56 / RMSE=0.21 / r=0.77 / MAE=0.165 | `reproduce_raman_calibration.py` |

## Method note (4 estimators)

The ensemble uses **four** estimators — kNN (color distance), Wasserstein (b* histogram),
FFT texture, and spatial pattern. A kinetic (exponential-decay) estimator was considered
but excluded from the final ensemble because its end-point extrapolation inflated the
leave-one-out error; see `loo_no_kinetic.py`. The estimator set is the single constant
`ENSEMBLE_METHODS` in `hfs2_v5_49.py`.
