# 투고 논문 pseudo-Raman 보정 지표 재현 — R2=0.56 / RMSE=0.21 / r=0.77 / MAE=0.165
"""영상 색기술자(b*, S, YI, ΔE) → 측정 Raman A1g intensity 의 4-OLS R²-가중 앙상블을
leave-one-out(20 image–Raman pairs) 으로 검증해 논문 §3.3 의 전체 지표를 재현한다.
  MPLBACKEND=Agg python3 tools/reproduce_raman_calibration.py

근거: paper/export_fig5_v4_data.py 의 fit_ols/predict/cross_validate 로직 추출(결정론적).
측정 A1g(MEASURED_A1G)은 4 조건 × 5 시점(0,3,7,14,28d) = 20쌍의 정규화 A1g(0d=1)이며
raman.raman.db 의 norm_peak 와 동일한 측정값이다.
"""
from __future__ import annotations
import os, sqlite3, statistics
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _first_existing(*cands):
    for c in cands:
        if os.path.exists(c): return c
    return cands[0]


DB_ALL = _first_existing(os.path.join(ROOT, "dbfiles/alldata.db"),
                         os.path.join(ROOT, "newfiles/output/output_cut/db/alldata.db"))
CONDS = ["NativeHfS2-35%RH", "NativeHfS2-70%RH", "Al2O3HfS2-70%RH", "PMMA HfS2-70%RH"]
DAYS = [0, 3, 7, 14, 28]
# 측정 정규화 A1g intensity (0d=1) — 4 조건 × 5 시점 = 20 image–Raman pairs
MEASURED_A1G = {
    "NativeHfS2-35%RH": [1.000, 0.85, 0.70, 0.55, 0.399],
    "NativeHfS2-70%RH": [1.000, 0.500, 0.10, 0.06, 0.060],
    "Al2O3HfS2-70%RH": [1.000, 0.97, 0.94, 0.90, 0.865],
    "PMMA HfS2-70%RH": [1.000, 0.83, 0.66, 0.500, 0.527],
}


def load_color():
    con = sqlite3.connect(f"file:{DB_ALL}?mode=ro", uri=True)
    out = {}
    for cond in CONDS:
        cd = {}
        for d in DAYS:
            rows = con.execute(
                "SELECT lab_b, s_mean, yellowness_idx, delta_e FROM images "
                "WHERE cond=? AND day=?", (cond, str(d))).fetchall()
            if rows:
                vals = {}
                for k, key in enumerate(("b", "S", "YI", "dE")):
                    arr = [r[k] for r in rows if r[k] is not None]
                    vals[key] = statistics.mean(arr) if arr else None
                cd[d] = vals
        out[cond] = cd
    con.close()
    return out


def fit_ols(X, y):
    X = np.asarray(X, float); y = np.asarray(y, float); n = len(X)
    if n < 2: return 0, 0, 0, 1
    xm, ym = X.mean(), y.mean()
    Sxx = ((X - xm) ** 2).sum(); Sxy = ((X - xm) * (y - ym)).sum()
    if Sxx == 0: return float(ym), 0, 0, float(y.std())
    beta = Sxy / Sxx; alpha = ym - beta * xm
    yh = alpha + beta * X
    ss_res = ((y - yh) ** 2).sum(); ss_tot = ((y - ym) ** 2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    sigma = np.sqrt(ss_res / (n - 2)) if n > 2 else np.sqrt(ss_res / max(n - 1, 1))
    return float(alpha), float(beta), float(max(0, r2)), float(sigma)


def predict(metrics, train_X, train_y):
    fits = {}
    for k in ("b", "S", "YI", "dE"):
        if k in train_X and metrics.get(k) is not None:
            a, b, r2, s = fit_ols(train_X[k], train_y)
            fits[k] = (a + b * metrics[k], max(0, r2), s)
    if not fits: return None
    w = np.array([r2 for _, r2, _ in fits.values()])
    if w.sum() == 0: w = np.ones(len(fits))
    w = w / w.sum()
    p = np.array([p for p, _, _ in fits.values()])
    return float((w * p).sum())


def main():
    color = load_color()
    pts = []
    for cond in CONDS:
        for i, d in enumerate(DAYS):
            m = color[cond].get(d)
            if m and all(m.get(k) is not None for k in ("b", "S", "YI", "dE")):
                pts.append((cond, d, m["b"], m["S"], m["YI"], m["dE"], MEASURED_A1G[cond][i]))
    refs, preds = [], []
    for i in range(len(pts)):
        train = pts[:i] + pts[i + 1:]
        tX = {"b": [p[2] for p in train], "S": [p[3] for p in train],
              "YI": [p[4] for p in train], "dE": [p[5] for p in train]}
        ty = [p[6] for p in train]
        _, _, b, s, yi, de, gt = pts[i]
        mu = predict({"b": b, "S": s, "YI": yi, "dE": de}, tX, ty)
        refs.append(gt); preds.append(mu)
    refs = np.array(refs); preds = np.array(preds)
    n = len(refs)
    err = preds - refs
    rmse = float(np.sqrt(np.mean(err ** 2)))
    mae = float(np.mean(np.abs(err)))
    r = float(np.corrcoef(refs, preds)[0, 1])
    ss_res = float(np.sum(err ** 2)); ss_tot = float(np.sum((refs - refs.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    print(f"[raman] leave-one-out over {n} image-Raman pairs (4-OLS R²-weighted ensemble)\n")
    print(f"  R²    = {r2:.2f}   (paper 0.56)")
    print(f"  RMSE  = {rmse:.2f}   (paper 0.21)")
    print(f"  r     = {r:.2f}   (paper 0.77)")
    print(f"  MAE   = {mae:.3f}  (paper 0.165)")


if __name__ == "__main__":
    main()
