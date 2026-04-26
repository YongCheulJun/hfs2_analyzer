"""
Advanced ensemble weight 헤드리스 최적화 (Tk 없이 WSL 에서 실행).

분석대상 = pkw_1.db (LOAD)
평가대상 = sample/*.jpg (파일명에서 day/cond 파싱)
각 평가대상을 query, pkw_1.db 의 매칭 이미지 제외 pool 로 5 methods
estimate (KNN/Wass/FFT/Spatial/Kinetic) → optimize_advanced_weights →
RMSE 최소화 가중치.

사용법:
  MPLBACKEND=Agg python3 tools/optimize_weights_headless.py
"""
from __future__ import annotations

import os
import re
import sys

# Tk 없이 사용 — matplotlib backend 강제
os.environ.setdefault("MPLBACKEND", "Agg")

# 프로젝트 루트
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
from PIL import Image

from hfs2_v5_49 import (
    db_load_all,
    parse_filename_tags,
    auto_detect_roi,
    roi_to_mask,
    compute_lab_metrics, compute_s_mean,
    compute_yellow_ratio, compute_yellowness_index,
    adv_precompute_pool,
    adv_hist_signature,
    adv_fft_features,
    adv_spatial_features,
    adv_wasserstein_estimate,
    adv_fft_estimate,
    adv_spatial_estimate,
    adv_kinetic_fit,
    adv_kinetic_estimate,
    adv_ensemble,
    optimize_advanced_weights,
    rgb_to_hsi,
)


def headless_knn(target: dict, pool: list,
                 w_b: float = 0.45, w_s: float = 0.30,
                 w_yi: float = 0.25):
    """_pred_compute_one 의 KNN 부분만 헤드리스 재현.

    cond_hint 가 있으면 같은 cond 풀로 필터링, 없으면 전체.
    Returns (est_day, confidence)."""
    cond_input = (target.get("cond_hint") or target.get("cond") or "").strip()
    ref_pool = pool
    if cond_input:
        same = [im for im in pool if im.get("cond") == cond_input]
        if same:
            ref_pool = same
    if not ref_pool:
        return None, 0

    def _safe(v):
        try:
            return 0.0 if (v is None or np.isnan(float(v))) else float(v)
        except Exception:
            return 0.0

    all_b  = [_safe(im["lab"]["b"])       for im in ref_pool]
    all_s  = [_safe(im["s_mean"])         for im in ref_pool]
    all_yi = [_safe(im["yellowness_idx"]) for im in ref_pool]

    def norm_range(vals):
        mn, mx = min(vals), max(vals)
        r = mx - mn if mx != mn else 1.0
        return mn, r

    b_mn, b_r   = norm_range(all_b)
    s_mn, s_r   = norm_range(all_s)
    yi_mn, yi_r = norm_range(all_yi)

    t_b  = (_safe(target["lab"]["b"])       - b_mn)  / b_r
    t_s  = (_safe(target["s_mean"])         - s_mn)  / s_r
    t_yi = (_safe(target["yellowness_idx"]) - yi_mn) / yi_r

    wt = w_b + w_s + w_yi
    wbn, wsn, wyin = w_b/wt, w_s/wt, w_yi/wt

    scores = []
    for im in ref_pool:
        i_b  = (_safe(im["lab"]["b"])       - b_mn)  / b_r
        i_s  = (_safe(im["s_mean"])         - s_mn)  / s_r
        i_yi = (_safe(im["yellowness_idx"]) - yi_mn) / yi_r
        d = (wbn  * (t_b - i_b) ** 2 +
             wsn  * (t_s - i_s) ** 2 +
             wyin * (t_yi - i_yi) ** 2) ** 0.5
        scores.append((d, im))
    scores.sort(key=lambda x: x[0])
    top3 = scores[:3]
    days_w = []
    for dist, im in top3:
        try:
            days_w.append((float(im["day"]), 1.0 / (dist + 1e-6)))
        except Exception:
            pass
    if not days_w:
        return None, 0
    total_w = sum(w for _, w in days_w)
    est_day = sum(d * w for d, w in days_w) / total_w
    conf = max(0.0, 100.0 - scores[0][0] * 200)
    return est_day, conf


def compute_methods_for_target(target: dict, pool: list) -> dict:
    """단일 query 에 대해 5 methods (knn/wass/fft/spatial/kinetic)."""
    rgb = target.get("rgb")
    mask = target.get("mask")
    roi = target.get("roi", (0, 0, rgb.shape[1], rgb.shape[0]))
    rows, cols = 3, 3

    adv_precompute_pool(pool, rows=rows, cols=cols)

    t_hist    = adv_hist_signature(rgb, mask)
    t_fft     = adv_fft_features(rgb, mask)
    t_spatial = adv_spatial_features(rgb, mask, roi, rows, cols)

    try:
        kp = adv_kinetic_fit(pool)
    except Exception:
        kp = {}

    w_res = adv_wasserstein_estimate(t_hist, pool)
    f_res = adv_fft_estimate(t_fft, pool)
    s_res = adv_spatial_estimate(t_spatial, pool, rows, cols)
    t_b = target.get("lab", {}).get("b", np.nan)
    k_res = adv_kinetic_estimate(t_b, kp, target.get("cond", ""))

    knn_d, knn_c = headless_knn(target, pool)

    return {
        "knn":     (knn_d,           knn_c),
        "wass":    (w_res["est_day"],  w_res["confidence"]),
        "fft":     (f_res["est_day"],  f_res["confidence"]),
        "spatial": (s_res["est_day"],  s_res["confidence"]),
        "kinetic": (k_res["est_day"],  k_res["confidence"]),
    }


def stem(s: str) -> str:
    return re.sub(r'\.(jpg|jpeg|png|bmp|tiff|tif)$', '', s or '',
                  flags=re.IGNORECASE)


def main():
    db_path = os.path.join(
        ROOT, "newfiles/output/output_cut/db/pkw_1.db")
    sample_dir = os.path.join(ROOT, "newfiles/output/sample")

    print(f"[load] DB: {db_path}")
    pool = db_load_all(db_path)
    # 분석 metric 들이 NaN 일 수 있음 (저장 전) → 즉석 계산
    n_recomputed = 0
    for im in pool:
        rgb = im.get("rgb")
        roi = im.get("roi")
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
            n_recomputed += 1
    if n_recomputed:
        print(f"[load] recomputed metrics for {n_recomputed} images")
    print(f"[load] pool size = {len(pool)}")

    # sample 폴더 — 평가대상 (jpg)
    img_files = sorted(
        f for f in os.listdir(sample_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    )
    print(f"[load] sample dir = {sample_dir} ({len(img_files)} files)")

    # 평가대상 → 분석대상 매칭 + advanced 분석
    img_by_name = {im.get("name"): im for im in pool}
    img_by_stem = {stem(im.get("name", "")): im for im in pool}

    estimates = []
    skipped = []
    for fname in img_files:
        path = os.path.join(sample_dir, fname)
        try:
            pil = Image.open(path).convert("RGB")
            rgb = np.array(pil)
            day_p, cond_p = parse_filename_tags(fname)

            # 매칭 (확장자 무시 → cond+day)
            match = (img_by_name.get(fname)
                     or img_by_stem.get(stem(fname)))
            if match is None and cond_p and day_p:
                for im in pool:
                    if (im.get("cond") == cond_p
                            and str(im.get("day", "")) == day_p):
                        match = im
                        break
            if match is None:
                skipped.append((fname, "no match in pool"))
                continue

            try:
                true_day = float(match.get("day"))
            except Exception:
                skipped.append((fname, "match has no day"))
                continue

            # ROI / metrics 계산
            roi, _flag, _ = auto_detect_roi(rgb, cond=cond_p)
            mask = roi_to_mask(rgb.shape, roi)
            lab = compute_lab_metrics(rgb, mask)
            s_mean = compute_s_mean(rgb, mask)
            yi = compute_yellowness_index(rgb, mask)

            target = {
                "rgb":  rgb,
                "mask": mask,
                "roi":  roi,
                "lab":  lab,
                "s_mean": s_mean,
                "yellow_ratio": compute_yellow_ratio(rgb, mask),
                "yellowness_idx": yi,
                "cond": cond_p,
                "cond_hint": cond_p,
                "name": fname,
            }

            # leave-one-out: pool 에서 매칭 이미지 제외
            sub_pool = [im for im in pool if im is not match]

            m_results = compute_methods_for_target(target, sub_pool)
            estimates.append((true_day, m_results, fname, cond_p))
            print(f"  ✓ {fname:<40} cond={cond_p:<22} "
                  f"true={true_day:>4.0f}  "
                  f"knn={m_results['knn'][0] if m_results['knn'][0] is not None else '-':>5}  "
                  f"ens via uniform: "
                  + ", ".join(f"{m}={m_results[m][0]:.1f}" if m_results[m][0] is not None else f"{m}=-"
                              for m in ("knn","wass","fft","spatial","kinetic")))
        except Exception as ex:
            import traceback
            print(f"  ✗ {fname}: {type(ex).__name__}: {ex}")
            traceback.print_exc()
            skipped.append((fname, str(ex)))

    print(f"\n[opt] estimates collected = {len(estimates)} "
          f"(skipped = {len(skipped)})")
    if len(estimates) < 5:
        print("[opt] insufficient (<5) — abort")
        return

    # optimize
    plain_estimates = [(td, mr) for td, mr, _, _ in estimates]
    opt = optimize_advanced_weights(plain_estimates)

    methods = ["knn", "wass", "fft", "spatial", "kinetic"]
    print("\n=== Optimization Result ===")
    print(f"  Ground truth pairs: {len(estimates)}")
    print(f"  Baseline (uniform) RMSE: {opt['baseline_rmse']:.3f} d")
    print(f"  Optimized           RMSE: {opt['rmse']:.3f} d")
    if opt['baseline_rmse'] > 0:
        improve = (opt['baseline_rmse'] - opt['rmse']) \
                  / opt['baseline_rmse'] * 100
        print(f"  Improvement:             {improve:+.1f}%")
    print("\n  Per-method solo RMSE:")
    for m in methods:
        print(f"    {m:<8s} {opt['per_method_rmse'][m]:>6.2f} d")
    print("\n  Optimal weights:")
    for m in methods:
        print(f"    {m:<8s} {opt['weights'][m]*100:>5.1f}%")

    # 각 평가대상별 최적 weight 적용 ensemble
    print("\n=== Per-target predictions (optimized) ===")
    for true_day, mr, fname, cond_p in estimates:
        ens = adv_ensemble(
            mr["knn"][0],     mr["knn"][1],
            mr["wass"][0],    mr["wass"][1],
            mr["fft"][0],     mr["fft"][1],
            mr["spatial"][0], mr["spatial"][1],
            mr["kinetic"][0], mr["kinetic"][1],
            prior_weights=opt["weights"],
        )
        ens_d = ens.get("est_day")
        err = (ens_d - true_day) if ens_d is not None else float("nan")
        print(f"  {fname:<38} cond={cond_p:<22} true={true_day:>4.0f}  "
              f"pred={ens_d:>5.2f}  err={err:+.2f}")

    if skipped:
        print(f"\n[skipped {len(skipped)}]")
        for fn, why in skipped[:10]:
            print(f"  {fn}: {why}")


if __name__ == "__main__":
    main()
