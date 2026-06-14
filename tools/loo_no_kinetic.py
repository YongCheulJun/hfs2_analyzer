# kinetic 추정기 제외(4-method) vs 포함(5-method) nested LOO 비교
"""kinetic estimator 가 LOO 폭발의 주범인지 검증. 5-method와 4-method(no kinetic)를
동일 잣대(직접 Huber 최적화 + 가중평균 예측)로 in-sample / nested LOO 모두 계산해 비교.
  MPLBACKEND=Agg python3 tools/loo_no_kinetic.py
"""
from __future__ import annotations
import os, sys
os.environ.setdefault("MPLBACKEND", "Agg")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tools"))
import numpy as np
from PIL import Image
from collections import defaultdict
from scipy.optimize import minimize
from hfs2_v5_49 import (
    db_load_all, parse_filename_tags, auto_detect_roi, roi_to_mask,
    compute_lab_metrics, compute_s_mean, compute_yellow_ratio, compute_yellowness_index)
from optimize_weights_headless import compute_methods_for_target, stem

def _first_existing(*cands):
    for c in cands:
        if os.path.exists(c): return c
    return cands[0]
DB = _first_existing(os.path.join(ROOT, "dbfiles/alldata.db"),
                     os.path.join(ROOT, "newfiles/output/output_cut/db/alldata.db"))
SAMPLE = _first_existing(os.path.join(ROOT, "dataset/images"),
                         os.path.join(ROOT, "newfiles/output/output_cut"))
ALL5 = ["knn", "wass", "fft", "spatial", "kinetic"]
NO_K = ["knn", "wass", "fft", "spatial"]
HUBER_D = 5.0

# ---- estimates 수집 ----
pool = db_load_all(DB)
for im in pool:
    rgb, roi = im.get("rgb"), im.get("roi")
    if rgb is None or roi is None: continue
    if im.get("mask") is None: im["mask"] = roi_to_mask(rgb.shape, roi)
    lab = im.get("lab", {})
    if not lab.get("b") or np.isnan(float(lab.get("b", np.nan))):
        im["lab"] = compute_lab_metrics(rgb, im["mask"]); im["s_mean"] = compute_s_mean(rgb, im["mask"])
        im["yellow_ratio"] = compute_yellow_ratio(rgb, im["mask"]); im["yellowness_idx"] = compute_yellowness_index(rgb, im["mask"])
img_by_name = {im.get("name"): im for im in pool}
img_by_stem = {stem(im.get("name", "")): im for im in pool}
estimates = []
for fname in sorted(f for f in os.listdir(SAMPLE) if f.lower().endswith((".jpg", ".jpeg", ".png"))):
    try:
        rgb = np.array(Image.open(os.path.join(SAMPLE, fname)).convert("RGB"))
        day_p, cond_p = parse_filename_tags(fname)
        match = img_by_name.get(fname) or img_by_stem.get(stem(fname))
        if match is None and cond_p and day_p:
            for im in pool:
                if im.get("cond") == cond_p and str(im.get("day", "")) == str(day_p): match = im; break
        if match is None: continue
        td = float(match.get("day"))
        roi, _, _ = auto_detect_roi(rgb, cond=cond_p); mask = roi_to_mask(rgb.shape, roi)
        target = {"rgb": rgb, "mask": mask, "roi": roi, "lab": compute_lab_metrics(rgb, mask),
                  "s_mean": compute_s_mean(rgb, mask), "yellow_ratio": compute_yellow_ratio(rgb, mask),
                  "yellowness_idx": compute_yellowness_index(rgb, mask), "cond": cond_p, "cond_hint": cond_p, "name": fname}
        mr = compute_methods_for_target(target, [im for im in pool if im is not match])
        estimates.append((td, mr, fname, cond_p))
    except Exception as ex:
        import traceback; print(f"x {fname}: {ex}"); traceback.print_exc()
N = len(estimates)
print(f"[nok] estimates = {N}\n")

def opt(plain, methods):
    A = np.array([[mr[m][0] if mr[m][0] is not None else np.nan for m in methods] for _, mr in plain], float)
    y = np.array([td for td, _ in plain], float)
    cm = np.nanmean(A, axis=0); cm = np.where(np.isnan(cm), 0.0, cm)
    nm = np.isnan(A)
    if nm.any(): A[np.where(nm)] = np.take(cm, np.where(nm)[1])
    def loss(w):
        w = np.maximum(w, 0.0); s = w.sum()
        if s <= 0: return 1e12
        w = w / s; err = A @ w - y; ae = np.abs(err)
        h = np.where(ae <= HUBER_D, 0.5 * err * err, HUBER_D * (ae - 0.5 * HUBER_D))
        return float(h.mean())
    best_w = np.ones(len(methods)) / len(methods); best = loss(best_w)
    starts = [np.ones(len(methods)) / len(methods)]
    for i in range(len(methods)):
        s = np.full(len(methods), 0.05); s[i] = 0.80; starts.append(s)
    for x0 in starts:
        r = minimize(loss, x0, bounds=[(0, 1)] * len(methods), method="L-BFGS-B")
        if r.fun < best: best = r.fun; best_w = np.maximum(r.x, 0.0)
    best_w = best_w / best_w.sum()
    return {m: float(best_w[i]) for i, m in enumerate(methods)}

def predict(mr, w, methods):
    vals, ws = [], []
    for m in methods:
        v = mr[m][0]
        if v is not None: vals.append(float(v)); ws.append(w[m])
    if not ws: return None
    ws = np.array(ws)
    return float(np.mean(vals)) if ws.sum() <= 0 else float(np.dot(vals, ws / ws.sum()))

def rmse(errs):
    e = np.array([x for x in errs if x is not None and not np.isnan(x)], float)
    return float(np.sqrt(np.mean(e * e))) if len(e) else float("nan")

def evaluate(methods):
    plain = [(td, mr) for td, mr, _, _ in estimates]
    # global
    wg = opt(plain, methods)
    g_in = rmse([predict(mr, wg, methods) - td for td, mr, _, _ in estimates])
    g_loo = []
    for i in range(N):
        w = opt([plain[j] for j in range(N) if j != i], methods)
        g_loo.append(predict(estimates[i][1], w, methods) - estimates[i][0])
    g_loo = rmse(g_loo)
    # condition-specific (weighted-mean)
    by = defaultdict(list)
    for idx, (td, mr, fn, c) in enumerate(estimates): by[c].append(idx)
    pin, ploo, ns = {}, {}, {}
    for c, idxs in by.items():
        ns[c] = len(idxs)
        wc = opt([plain[j] for j in idxs], methods) if len(idxs) >= 3 else wg
        pin[c] = rmse([predict(estimates[j][1], wc, methods) - estimates[j][0] for j in idxs])
        el = []
        for j in idxs:
            others = [k for k in idxs if k != j]
            w = opt([plain[k] for k in others], methods) if len(others) >= 3 else wg
            el.append(predict(estimates[j][1], w, methods) - estimates[j][0])
        ploo[c] = rmse(el)
    c_in = sum(ns[c] * pin[c] for c in by) / N
    c_loo = sum(ns[c] * ploo[c] for c in by) / N
    # uniform
    uni = {m: 1.0 for m in methods}
    u = rmse([predict(mr, uni, methods) - td for td, mr, _, _ in estimates])
    return {"uniform": u, "g_in": g_in, "g_loo": g_loo, "c_in": c_in, "c_loo": c_loo,
            "per_cond_loo": ploo, "ns": ns}

r5 = evaluate(ALL5)
r4 = evaluate(NO_K)
print("=" * 74)
print("  RMSE (일)            5-method            4-method (no kinetic)")
print("                     in-sample  LOO        in-sample  LOO")
print("=" * 74)
print(f"  uniform            {r5['uniform']:>8.2f}{'':>11}{r4['uniform']:>8.2f}")
print(f"  global             {r5['g_in']:>8.2f}{r5['g_loo']:>8.2f}{'':>5}{r4['g_in']:>8.2f}{r4['g_loo']:>8.2f}")
print(f"  condition-specific {r5['c_in']:>8.2f}{r5['c_loo']:>8.2f}{'':>5}{r4['c_in']:>8.2f}{r4['c_loo']:>8.2f}")
print("\n  조건별 nested LOO RMSE (5-method → 4-method):")
for c in r5["per_cond_loo"]:
    print(f"    {c:<22} n={r5['ns'][c]:>2}  {r5['per_cond_loo'][c]:>6.2f} → {r4['per_cond_loo'][c]:>6.2f}")
