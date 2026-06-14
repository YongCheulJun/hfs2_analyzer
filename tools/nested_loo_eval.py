# nested leave-one-out 재평가 — 가중치 최적화를 fold 안으로 넣어 leakage 없는 RMSE 산출
"""
현 파이프라인은 앙상블 가중치를 전체 데이터로 한 번 최적화한 뒤 같은 데이터에
적용한 in-sample RMSE 를 보고한다(leakage). 본 스크립트는 estimates 수집은 동일하게
하되, 가중치 최적화를 각 LOO fold 안(query 제외 N-1)으로 옮겨 정직한 out-of-sample
RMSE 를 산출하고, in-sample 값과 나란히 비교한다. 새 실험·새 데이터 없음.

  MPLBACKEND=Agg python3 tools/nested_loo_eval.py
"""
from __future__ import annotations
import os, sys
os.environ.setdefault("MPLBACKEND", "Agg")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import numpy as np
from PIL import Image
from collections import defaultdict

from hfs2_v5_49 import (
    db_load_all, parse_filename_tags, auto_detect_roi, roi_to_mask,
    compute_lab_metrics, compute_s_mean, compute_yellow_ratio,
    compute_yellowness_index, adv_ensemble, optimize_advanced_weights,
)
from optimize_weights_headless import compute_methods_for_target, stem

def _first_existing(*cands):
    for c in cands:
        if os.path.exists(c): return c
    return cands[0]
DB = _first_existing(os.path.join(ROOT, "dbfiles/alldata.db"),
                     os.path.join(ROOT, "newfiles/output/output_cut/db/alldata.db"))
SAMPLE = _first_existing(os.path.join(ROOT, "dataset/images"),
                         os.path.join(ROOT, "newfiles/output/output_cut"))
METHODS = ["knn", "wass", "fft", "spatial", "kinetic"]

# ---------- pool 로드 + metric 보정 (헤드리스와 동일) ----------
pool = db_load_all(DB)
for im in pool:
    rgb, roi = im.get("rgb"), im.get("roi")
    if rgb is None or roi is None:
        continue
    if im.get("mask") is None:
        im["mask"] = roi_to_mask(rgb.shape, roi)
    lab = im.get("lab", {})
    if not lab.get("b") or np.isnan(float(lab.get("b", np.nan))):
        im["lab"] = compute_lab_metrics(rgb, im["mask"])
        im["s_mean"] = compute_s_mean(rgb, im["mask"])
        im["yellow_ratio"] = compute_yellow_ratio(rgb, im["mask"])
        im["yellowness_idx"] = compute_yellowness_index(rgb, im["mask"])
print(f"[load] pool = {len(pool)}")

img_files = sorted(f for f in os.listdir(SAMPLE)
                   if f.lower().endswith((".jpg", ".jpeg", ".png")))
img_by_name = {im.get("name"): im for im in pool}
img_by_stem = {stem(im.get("name", "")): im for im in pool}

# ---------- estimates 수집 (descriptor 단계는 LOO 그대로) ----------
estimates = []
for fname in img_files:
    try:
        rgb = np.array(Image.open(os.path.join(SAMPLE, fname)).convert("RGB"))
        day_p, cond_p = parse_filename_tags(fname)
        match = img_by_name.get(fname) or img_by_stem.get(stem(fname))
        if match is None and cond_p and day_p:
            for im in pool:
                if im.get("cond") == cond_p and str(im.get("day", "")) == str(day_p):
                    match = im; break
        if match is None:
            print(f"  skip {fname}: no match"); continue
        true_day = float(match.get("day"))
        roi, _, _ = auto_detect_roi(rgb, cond=cond_p)
        mask = roi_to_mask(rgb.shape, roi)
        target = {
            "rgb": rgb, "mask": mask, "roi": roi,
            "lab": compute_lab_metrics(rgb, mask),
            "s_mean": compute_s_mean(rgb, mask),
            "yellow_ratio": compute_yellow_ratio(rgb, mask),
            "yellowness_idx": compute_yellowness_index(rgb, mask),
            "cond": cond_p, "cond_hint": cond_p, "name": fname,
        }
        sub_pool = [im for im in pool if im is not match]
        mr = compute_methods_for_target(target, sub_pool)
        estimates.append((true_day, mr, fname, cond_p))
    except Exception as ex:
        import traceback
        print(f"  x {fname}: {type(ex).__name__}: {ex}")
        traceback.print_exc()

N = len(estimates)
print(f"[opt] estimates = {N}")
if N < 5:
    print("[opt] insufficient (<5) — abort"); sys.exit(1)

plain = [(td, mr) for td, mr, _, _ in estimates]

def predict(mr, w):
    ens = adv_ensemble(
        mr["knn"][0], mr["knn"][1], mr["wass"][0], mr["wass"][1],
        mr["fft"][0], mr["fft"][1], mr["spatial"][0], mr["spatial"][1],
        mr["kinetic"][0], mr["kinetic"][1], prior_weights=w)
    return ens.get("est_day")

def err_of(mr, w, td):
    p = predict(mr, w)
    return (p - td) if p is not None else None

def rmse(errs):
    e = np.array([x for x in errs if x is not None and not np.isnan(x)], dtype=float)
    return float(np.sqrt(np.mean(e * e))) if len(e) else float("nan")

# ===== 1) GLOBAL weight =====
opt_all = optimize_advanced_weights(plain)
w_glob = opt_all["weights"]
errs_g_in = [err_of(mr, w_glob, td) for td, mr, _, _ in estimates]
errs_g_loo = []
for i in range(N):
    train = [plain[j] for j in range(N) if j != i]
    w = optimize_advanced_weights(train)["weights"]
    errs_g_loo.append(err_of(estimates[i][1], w, estimates[i][0]))

# ===== 2) CONDITION-SPECIFIC weight =====
by_cond = defaultdict(list)
for idx, (td, mr, fn, cond) in enumerate(estimates):
    by_cond[cond].append(idx)

cond_n = {}
per_cond_in, per_cond_loo = {}, {}
for cond, idxs in by_cond.items():
    cond_n[cond] = len(idxs)
    sub = [plain[j] for j in idxs]
    w_c = optimize_advanced_weights(sub)["weights"] if len(sub) >= 3 else w_glob
    per_cond_in[cond] = rmse([err_of(estimates[j][1], w_c, estimates[j][0]) for j in idxs])
    e_loo = []
    for j in idxs:
        others = [plain[k] for k in idxs if k != j]
        w = optimize_advanced_weights(others)["weights"] if len(others) >= 3 else w_glob
        e_loo.append(err_of(estimates[j][1], w, estimates[j][0]))
    per_cond_loo[cond] = rmse(e_loo)
# 논문과 동일: n-가중 평균 RMSE
wmean_in  = sum(cond_n[c] * per_cond_in[c]  for c in by_cond) / N
wmean_loo = sum(cond_n[c] * per_cond_loo[c] for c in by_cond) / N

# ===== 3) UNIFORM baseline (학습 없음 → in-sample=loo) =====
base_rmse = opt_all["baseline_rmse"]

print("\n" + "=" * 66)
print("  RMSE (일) — in-sample(현 논문 방식)  vs  nested LOO(leakage 제거)")
print("=" * 66)
print(f"  {'모델':<26}{'in-sample':>14}{'nested LOO':>14}")
print(f"  {'uniform baseline':<26}{base_rmse:>14.2f}{base_rmse:>14.2f}")
print(f"  {'global weight':<26}{rmse(errs_g_in):>14.2f}{rmse(errs_g_loo):>14.2f}")
print(f"  {'condition-specific (wmean)':<26}{wmean_in:>14.2f}{wmean_loo:>14.2f}")
print("\n  조건별 RMSE (in-sample → nested LOO):")
for c in by_cond:
    print(f"    {c:<22} n={cond_n[c]:>2}  {per_cond_in[c]:>6.2f} → {per_cond_loo[c]:>6.2f}")
print(f"\n  논문 보고값(모두 in-sample): uniform 7.74 / global 6.30 / cond-specific 4.80")
