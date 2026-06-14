# 투고 논문(4-method) 핵심 수치 재현 — 산화3조건 global-weight strict LOO = 3.30일 등
"""HfS2 Image-based oxidation 04.docx 가 보고하는 4-method 수치를 결정론적으로 재현.
  MPLBACKEND=Agg python3 tools/reproduce_paper_4method.py

검증 대상(논문 보고값):
  - 산화3조건(Native35/Native70/PMMA) global-weight strict LOO RMSE = 3.30 d
  - 산화3조건 uniform = 6.32 d, condition-specific = 4.17 d
  - Al2O3 = 약 10 d (모든 scheme)
  - kNN per-cond solo: N35 3.12, N70 3.56
모든 추정기·가중치 최적화는 난수 없는 결정론적 경로(고정 multi-start + L-BFGS-B).
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
# 클론 직후엔 추적본(dbfiles/·dataset/), 개발 트리엔 newfiles/ 사용
DB = _first_existing(os.path.join(ROOT, "dbfiles/alldata.db"),
                     os.path.join(ROOT, "newfiles/output/output_cut/db/alldata.db"))
SAMPLE = _first_existing(os.path.join(ROOT, "dataset/images"),
                         os.path.join(ROOT, "newfiles/output/output_cut"))
M4 = ["knn", "wass", "fft", "spatial"]              # 4-method (kinetic 제외)
OXIDIZING = ["NativeHfS2-35%RH", "NativeHfS2-70%RH", "PMMA HfS2-70%RH"]
HUBER_D = 5.0

# ---- estimates 수집 (LOO: 타깃을 풀에서 제외) ----
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
estimates = []  # (true_day, methods_result, fname, cond)
for fname in sorted(f for f in os.listdir(SAMPLE) if f.lower().endswith((".jpg", ".jpeg", ".png"))):
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
N = len(estimates)
print(f"[repro] estimates = {N}\n")


def opt(plain, methods):
    """Huber-loss 최소화 global weight (난수 없는 고정 multi-start)."""
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
    return {m: float(best_w[i] / best_w.sum()) for i, m in enumerate(methods)}


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


# 인덱스 부분집합 위에서 global-weight strict LOO (각 fold 에서 query 를 가중치학습·풀 양쪽 제외)
def global_loo(idxs):
    plain = [(estimates[i][0], estimates[i][1]) for i in idxs]
    errs = []
    for pos, i in enumerate(idxs):
        w = opt([plain[k] for k in range(len(idxs)) if k != pos], M4)
        errs.append(predict(estimates[i][1], w, M4) - estimates[i][0])
    return rmse(errs)


def uniform_rmse(idxs):
    uni = {m: 1.0 for m in M4}
    return rmse([predict(estimates[i][1], uni, M4) - estimates[i][0] for i in idxs])


def condspec_loo(idxs):
    """그 부분집합을 조건별로 쪼개 조건별 weight 로 strict LOO, n-가중평균."""
    by = defaultdict(list)
    for i in idxs: by[estimates[i][3]].append(i)
    tot, num = 0, 0
    for c, ci in by.items():
        plain = [(estimates[i][0], estimates[i][1]) for i in ci]
        errs = []
        for pos, i in enumerate(ci):
            others = [k for k in range(len(ci)) if k != pos]
            w = opt([plain[k] for k in others], M4) if len(others) >= 3 else opt(plain, M4)
            errs.append(predict(estimates[i][1], w, M4) - estimates[i][0])
        tot += len(ci) * rmse(errs); num += len(ci)
    return tot / num


by_cond = defaultdict(list)
for i, (_, _, _, c) in enumerate(estimates): by_cond[c].append(i)

ox_idx = [i for i, (_, _, _, c) in enumerate(estimates) if c in OXIDIZING]
al_idx = [i for i, (_, _, _, c) in enumerate(estimates) if c == "Al2O3HfS2-70%RH"]

print("=" * 60)
print("  투고논문 4-method 핵심수치 재현")
print("=" * 60)
print(f"\n  [산화 3조건] (Native35 + Native70 + PMMA, n={len(ox_idx)})")
print(f"    uniform              RMSE = {uniform_rmse(ox_idx):5.2f} d   (논문 6.32)")
print(f"    global-weight  strict LOO = {global_loo(ox_idx):5.2f} d   (논문 3.30  ← 헤드라인)")
print(f"    condition-specific    LOO = {condspec_loo(ox_idx):5.2f} d   (논문 4.17)")
print(f"\n  [Al2O3 단독] (n={len(al_idx)}, 적용범위 밖)")
print(f"    global-weight  strict LOO = {global_loo(al_idx):5.2f} d   (논문 약 10)")

print("\n  [개별 kNN per-cond solo RMSE]  (논문: N35 3.12, N70 3.56)")
for c, idxs in sorted(by_cond.items()):
    e = [estimates[i][1]["knn"][0] - estimates[i][0] for i in idxs if estimates[i][1]["knn"][0] is not None]
    print(f"    {c:<22} n={len(idxs):>2}  kNN = {rmse(e):5.2f} d")
