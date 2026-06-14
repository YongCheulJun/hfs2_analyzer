# HfS2 Image-Based Oxidation Aging Analyzer

This repository accompanies the paper

> **Raman-Calibrated Image-Based Screening of Native Oxidation Aging in CVD-Grown HfS2 Thin Films on Sapphire**
> Yongcheul Jun and Kwangwook Park (corresponding author, kwangwook.park@jbnu.ac.kr)

It contains the image-processing pipeline, the bundled analysis dataset
(`dbfiles/alldata.db` + the 33 sample photographs in `dataset/images/`), and the
headless utilities required to reproduce the four-estimator ensemble and Raman
calibration results reported in the main text. A fresh clone reproduces every
reported number with a single command — see [`REPRODUCE.md`](REPRODUCE.md).

## Contents

- [Quick start](#quick-start)
- [Repository contents](#repository-contents)
- [Database 1: `dbfiles/pkw_1.db`](#database-1-dbfilespkw_1db)
- [Database 2: `dbfiles/raman.raman.db`](#database-2-dbfilesramaramandb)
- [Reproducing the main-text analysis](#reproducing-the-main-text-analysis)
- [Dependencies](#dependencies)
- [Citation](#citation)
- [Contact](#contact)
- [License](#license)

---

## Quick start

```bash
git clone https://github.com/YongCheulJun/hfs2_analyzer.git
cd hfs2_analyzer
pip install -r requirements.txt

# Launch the desktop GUI (Windows native Python recommended)
python hfs2_v5_49.py
```

All data is bundled with the repository — no separate download is required:
the 33-image analysis pool (`dbfiles/alldata.db` + `dataset/images/`), the
20-image Raman-linked subset (`dbfiles/pkw_1.db`), and the Raman A1g
intensities (`dbfiles/raman.raman.db`). To reproduce the paper's numbers
without the GUI, run `python tools/reproduce_paper_4method.py`.

---

## Repository contents

| Path | Description |
| --- | --- |
| `hfs2_v5_49.py` | Single-file Tkinter desktop application (~16,000 LOC) |
| `tools/eval_roi.py` | Headless ROI accuracy evaluation |
| `tools/optimize_weights_headless.py` | Headless ensemble-weight optimisation |
| `tools/reproduce_paper_4method.py` | Reproduces the main-text aging-day numbers (3.30 d headline) |
| `tools/reproduce_raman_calibration.py` | Reproduces the Raman calibration metrics (R²=0.56, …) |
| `tools/loo_no_kinetic.py`, `tools/nested_loo_eval.py` | 5- vs 4-method and leakage cross-checks |
| `dbfiles/alldata.db` | 33-image analysis pool (descriptors + ROIs) — main reproduction data |
| `dataset/images/` | The 33 sample photographs (PNG) |
| `dbfiles/pkw_1.db` | 20-image Raman-linked subset with manually-verified ROI coordinates |
| `dbfiles/raman.raman.db` | Time-resolved Raman A1g intensity for the four passivation/humidity conditions |
| `REPRODUCE.md`, `dbfiles/CHECKSUMS.md5` | Reproduction guide and data checksums |
| `requirements.txt` | Python dependencies |

The GUI source code (`hfs2_v5_49.py`) and headless tools cover the full
pipeline reported in the paper: ROI extraction, colour/texture descriptors,
four descriptor-based aging-day estimators (kNN, Wasserstein, FFT, spatial;
a kinetic estimator was evaluated but excluded from the final ensemble),
Huber-loss ensemble weighting, and Raman-calibrated A1g intensity
(pseudo-Raman) estimation.

---

## Database 1: `dbfiles/pkw_1.db`

SQLite database storing the 20 specimen photographs (4 passivation/humidity
conditions × 5 aging days) together with their final ROI coordinates and
pre-computed image descriptors. This is the "image" half of the 20
image–Raman pairs used to anchor the Raman-calibrated A1g intensity
estimation. The ROI for each specimen was first detected automatically (HSV
mask + convex hull, condition-specific area 13–17%); a small number of
specimens whose automatic boundary misidentified the sample were adjusted
manually before storage.

`images` table columns:

| Column | Description |
| --- | --- |
| `id` | Row id |
| `name` | Sample image filename (`<day>day_<RH>RH_<cond>.jpg`) |
| `cond` | Passivation/humidity condition |
| `day` | Aging day (0, 3, 7, 14, 28) |
| `roi_x0`, `roi_y0`, `roi_x1`, `roi_y1` | Final ROI rectangle (image coordinates), automatic with manual review where needed |
| `lab_L`, `lab_a`, `lab_b` | CIE Lab values (ROI pixel mean) |
| `s_mean` | HSI saturation channel mean (ROI pixel mean) |
| `yellowness_idx` | ASTM E313 Yellowness Index (ROI pixel mean) |
| `delta_e` | CIE 1976 colour difference vs. day-0 of the same condition |
| `yellow_ratio` | Pixel ratio inside the yellow region of the ROI |
| `glcm_con`, `glcm_eng`, `glcm_hom`, `glcm_cor` | GLCM texture descriptors |
| `stats_json` | Auxiliary statistics in JSON form |
| `rgb_blob`, `thumb_blob` | (optional) image blobs |
| `saved_at` | Last-saved timestamp |

Quick read with Python:

```python
import sqlite3
con = sqlite3.connect("dbfiles/pkw_1.db")
for cond, day, b, x0, y0, x1, y1 in con.execute(
    "SELECT cond, day, lab_b, roi_x0, roi_y0, roi_x1, roi_y1 "
    "FROM images ORDER BY cond, CAST(day AS REAL)"
):
    print(f"{cond:25s} day={day:>3}  b*={b:6.2f}  ROI=({x0},{y0})-({x1},{y1})")
con.close()
```

---

## Database 2: `dbfiles/raman.raman.db`

SQLite database storing the time-resolved Raman A1g intensity used as the
calibration target for the pseudo-Raman estimation in the main text.

`raman_data` table columns:

| Column | Description |
| --- | --- |
| `id` | Row id |
| `cond` | Passivation/humidity condition |
| `day` | Aging day (0, 3, 7, 14, 28) |
| `peak` | A1g peak height (a.u.) |
| `norm_peak` | Normalised A1g intensity (day-0 of the same condition = 1.00) |
| `peak_shift` | A1g peak position (cm-1) |
| `peak_range` | (optional) integration range used for the peak |
| `spectrum_json` | Full Raman spectrum (JSON: `{"shifts": [...], "intensities": [...]}`) |
| `saved_at` | Last-saved timestamp |

Quick read:

```python
import sqlite3, json
con = sqlite3.connect("dbfiles/raman.raman.db")
for cond, day, peak, norm, shift, spec in con.execute(
    "SELECT cond, day, peak, norm_peak, peak_shift, spectrum_json "
    "FROM raman_data ORDER BY cond, CAST(day AS REAL)"
):
    sp = json.loads(spec)
    print(f"{cond:25s} day={day:>3}  norm_A1g={norm:.3f}  "
          f"peak={peak:.3f} a.u.  shift={shift:.2f} cm-1  "
          f"({len(sp['shifts'])} spectrum points)")
con.close()
```

---

## Reproducing the main-text analysis

The headline aging-day numbers are reproduced with **one command** from the
bundled data (`dbfiles/alldata.db` + the 33 images in `dataset/images/`). The
pipeline is deterministic, so a fresh clone yields the paper's values exactly.
See [`REPRODUCE.md`](REPRODUCE.md) for the full number-to-command mapping and
expected output.

```bash
export MPLBACKEND=Agg
python tools/reproduce_paper_4method.py
```

This prints the four-estimator results for the three oxidizing conditions:
global-weight strict leave-one-out RMSE **3.30 d** (headline), uniform 6.32 d,
condition-specific 4.17 d, Al₂O₃ ≈ 10 d, and the per-condition kNN RMSEs
(3.12 d / 3.56 d).

### Supporting checks

```bash
python tools/loo_no_kinetic.py     # 5- vs 4-method (why the kinetic estimator is excluded)
python tools/nested_loo_eval.py    # in-sample vs nested leave-one-out (leakage check)
```

### Ensemble-weight optimisation (global weights)

```bash
python tools/optimize_weights_headless.py \
    --pool dbfiles/alldata.db \
    --targets dataset/images
```

Trains the four-estimator Huber-loss optimal weights; the global weights
concentrate on kNN (≈0.85) with a smaller spatial contribution (≈0.15),
consistent with the paper. Add `--save` to write them to `settings.json` for
the GUI.

### Inspect ROIs and descriptors in the GUI

```bash
python hfs2_v5_49.py
```

In the toolbar, click **Load All** → select `dbfiles/alldata.db` to browse the
33 specimens with their stored ROIs and descriptors.

---

## Dependencies

- Python 3.10 or newer (Windows native Python recommended for the GUI)
- `numpy`, `opencv-python`, `Pillow`, `matplotlib`, `scipy`
- `tkinterdnd2` (drag-and-drop in the GUI)
- `python-docx` (report export)
- `anthropic` (optional, AI-analysis tab)

A pinned list is provided in `requirements.txt`.

The GUI reads and writes SQLite database files using a `tempfile.mkdtemp()`
+ `shutil.move` pattern, which avoids the file-locking issues that arise
when SQLite is used directly on a 9p-mounted Windows–WSL share.

---

## Citation

If you use this code or the accompanying databases in your work, please cite
the corresponding paper above. The bibliographic entry will be added once the
DOI is assigned.

---

## Contact

- Yongcheul Jun — junyc@mystar24.com
- Kwangwook Park (corresponding author) — kwangwook.park@jbnu.ac.kr

---

## License

Provided for academic and review use. A formal licence will be added on
publication of the paper.
