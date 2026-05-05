# HfS2 Image-Based Oxidation Aging Analyzer

This repository accompanies the paper

> **Raman-Calibrated Image-Based Screening of Native Oxidation Aging in CVD-Grown HfS2 Thin Films on Sapphire**
> Yongcheul Jeon and Kwangwook Park (corresponding author, kwangwook.park@jbnu.ac.kr)

It contains the image-processing pipeline, two reference databases used in the
paper, and the headless utilities required to reproduce the per-method and
ensemble accuracy comparison reported in the main text.

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

The two reference databases (`dbfiles/pkw_1.db` and `dbfiles/raman.raman.db`)
are bundled with the repository — no separate download is required. Inside
the GUI, click **Load All** and select either database to populate the
workspace with the 20 image–Raman pairs used in the paper.

---

## Repository contents

| Path | Description |
| --- | --- |
| `hfs2_v5_49.py` | Single-file Tkinter desktop application (~16,000 LOC) |
| `tools/eval_roi.py` | Headless ROI accuracy evaluation |
| `tools/optimize_weights_headless.py` | Headless ensemble-weight optimisation |
| `tools/extract_pptx_to_db_format.py` | PPTX → image extractor utility |
| `tools/center_crop_images.py` | Centre-crop helper |
| `dbfiles/pkw_1.db` | Sample dataset (20 specimens) with manually-verified ROI coordinates |
| `dbfiles/raman.raman.db` | Time-resolved Raman A1g intensity for the four passivation/humidity conditions |
| `requirements.txt` | Python dependencies |

The GUI source code (`hfs2_v5_49.py`) and headless tools cover the full
pipeline reported in the paper: ROI extraction, colour/texture descriptors,
five descriptor-based aging-day estimators, Huber-loss ensemble weighting,
and Raman-calibrated A1g intensity (pseudo-Raman) estimation.

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

### 1. Inspect ROIs and descriptors in the GUI

```bash
python hfs2_v5_49.py
```

In the toolbar, click **Load All** → select `dbfiles/pkw_1.db`. The 20
specimens appear in the left panel with their stored ROI rectangles. Click
any card to inspect the colour/texture descriptors and the Raman match (if
any).

### 2. Headless ROI accuracy check

```bash
python tools/eval_roi.py dbfiles/pkw_1.db
```

Reports per-specimen ROI quality, area ratio, and inter-condition consistency.

### 3. Headless ensemble-weight optimisation

```bash
python tools/optimize_weights_headless.py \
    --pool dbfiles/pkw_1.db \
    --targets path/to/your/specimen/photos \
    --save
```

Trains the per-condition Huber-loss optimal ensemble weights and writes them
to the project's `settings.json` so that the GUI picks them up on next start.

### 4. Stand-alone leave-one-out check on the bundled databases

The two bundled databases are sufficient to reproduce the per-condition
Pearson correlations between aging day and the colour metrics — the building
block used by every estimator in the paper:

```python
import sqlite3, statistics

con = sqlite3.connect("dbfiles/pkw_1.db")
by_cond = {}
for cond, day, b, s, yi in con.execute(
    "SELECT cond, day, lab_b, s_mean, yellowness_idx FROM images"
):
    by_cond.setdefault(cond, []).append((float(day), b, s, yi))
con.close()

def pearson(xs, ys):
    n = len(xs); mx = sum(xs)/n; my = sum(ys)/n
    num = sum((x - mx)*(y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx)**2 for x in xs) * sum((y - my)**2 for y in ys)) ** 0.5
    return num/den if den else float("nan")

for cond, rows in by_cond.items():
    rows.sort()
    days, bs, ss, yis = zip(*rows)
    print(f"{cond:25s}  r(day, b*) = {pearson(days, bs):+.2f}  "
          f"r(day, S) = {pearson(days, ss):+.2f}  "
          f"r(day, YI) = {pearson(days, yis):+.2f}")
```

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

- Yongcheul Jeon — junyc@mystar24.com
- Kwangwook Park (corresponding author) — kwangwook.park@jbnu.ac.kr

---

## License

Provided for academic and review use. A formal licence will be added on
publication of the paper.
