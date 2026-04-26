"""
ROI 자동 검출 평가 스크립트 (headless, WSL 가능).

사용법:
  python3 tools/eval_roi.py <manual.db> [--auto-db <auto.db>]

- <manual.db>: 사용자 수동 ROI (정답)
- --auto-db (선택): 비교 대상 자동 DB. 미지정 시 hfs2_v5_49.auto_detect_roi 로
  manual.db 의 이미지를 다시 돌려 새 자동 ROI 를 만들어 비교.

출력:
  이미지별 IoU/면적비/중심변위 표 + 통계 요약 (전체 + cond 그룹별).
"""
from __future__ import annotations

import argparse
import io
import os
import sqlite3
import statistics
import sys
from collections import defaultdict

import numpy as np
from PIL import Image


def _blob_to_rgb(blob: bytes) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(blob)).convert("RGB"))


def _load_db(path: str):
    con = sqlite3.connect(path)
    rows = con.execute(
        "SELECT name, day, cond, roi_x0, roi_y0, roi_x1, roi_y1, rgb_blob "
        "FROM images ORDER BY name"
    ).fetchall()
    con.close()
    out = []
    for r in rows:
        name, day, cond, x0, y0, x1, y1, rgb_blob = r
        rgb = _blob_to_rgb(rgb_blob) if rgb_blob else None
        out.append({
            "name": name, "day": day, "cond": cond,
            "roi": (x0, y0, x1, y1),
            "rgb": rgb,
            "shape": rgb.shape if rgb is not None else None,
        })
    return out


def _iou(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0); iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1); iy1 = min(ay1, by1)
    iw = max(0, ix1 - ix0); ih = max(0, iy1 - iy0)
    inter = iw * ih
    aa = max(0, ax1 - ax0) * max(0, ay1 - ay0)
    bb = max(0, bx1 - bx0) * max(0, by1 - by0)
    uni = aa + bb - inter
    return inter / uni if uni > 0 else 0.0


def _area(roi):
    return max(0, roi[2] - roi[0]) * max(0, roi[3] - roi[1])


def _center(roi):
    return ((roi[0] + roi[2]) / 2, (roi[1] + roi[3]) / 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manual_db")
    ap.add_argument("--auto-db", default=None,
                    help="비교 대상 자동 DB. 없으면 auto_detect_roi 로 재계산.")
    ap.add_argument("--module-dir", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))),
        help="hfs2_v5_49 가 있는 디렉토리 (기본: 스크립트 상위)")
    args = ap.parse_args()

    sys.path.insert(0, args.module_dir)

    manual = _load_db(args.manual_db)
    print(f"manual rows = {len(manual)}  ({args.manual_db})")

    if args.auto_db:
        auto_rows = _load_db(args.auto_db)
        auto_map = {r["name"]: r["roi"] for r in auto_rows}
        source = f"DB ({args.auto_db})"
    else:
        # 새 auto_detect_roi 로 즉석 계산
        from hfs2_v5_49 import auto_detect_roi
        auto_map = {}
        for r in manual:
            if r["rgb"] is None:
                continue
            roi, flag, _ = auto_detect_roi(r["rgb"], cond=r["cond"])
            auto_map[r["name"]] = roi
        source = "auto_detect_roi (live)"

    print(f"auto source = {source}\n")

    rows = []
    for r in manual:
        name = r["name"]
        m_roi = r["roi"]
        a_roi = auto_map.get(name)
        if a_roi is None or r["shape"] is None:
            continue
        h, w = r["shape"][:2]
        iou = _iou(a_roi, m_roi)
        m_area = _area(m_roi); a_area = _area(a_roi)
        area_ratio = (a_area / m_area) if m_area > 0 else 0.0
        ax, ay = _center(a_roi); mx, my = _center(m_roi)
        dx = ax - mx; dy = ay - my
        dist = (dx * dx + dy * dy) ** 0.5
        manual_area_pct = m_area / (h * w) * 100
        rows.append({
            "name": name, "cond": r["cond"], "day": r["day"],
            "iou": iou, "area_ratio": area_ratio,
            "dist": dist, "dx": dx, "dy": dy,
            "m_pct": manual_area_pct,
        })

    # 표
    print(f"{'name':<40} {'cond':<22} {'IoU':>6} {'area':>6} "
          f"{'dist':>6} {'mPct':>6}")
    print("-" * 92)
    for r in sorted(rows, key=lambda x: x["iou"]):
        print(f"{r['name']:<40} {r['cond']:<22} "
              f"{r['iou']:>6.3f} {r['area_ratio']:>6.3f} "
              f"{r['dist']:>6.1f} {r['m_pct']:>6.1f}")

    if not rows:
        print("\n(매칭 행 없음)")
        return

    ious = [r["iou"] for r in rows]
    ars = [r["area_ratio"] for r in rows]
    dists = [r["dist"] for r in rows]
    dxs = [r["dx"] for r in rows]; dys = [r["dy"] for r in rows]
    mpcts = [r["m_pct"] for r in rows]

    def _stat(label, vals):
        print(f"  {label:<14} mean={statistics.mean(vals):>7.3f}  "
              f"median={statistics.median(vals):>7.3f}  "
              f"min={min(vals):>7.3f}  max={max(vals):>7.3f}")

    print(f"\n=== Summary (n={len(rows)}) ===")
    _stat("IoU",         ious)
    _stat("area_ratio",  ars)
    _stat("dist (px)",   dists)
    _stat("dx (px)",     dxs)
    _stat("dy (px)",     dys)
    _stat("manual %",    mpcts)

    # cond 그룹별
    by_cond = defaultdict(list)
    for r in rows:
        by_cond[r["cond"] or ""].append(r)
    print("\n=== Per cond ===")
    for cond, grp in sorted(by_cond.items()):
        ious_g = [r["iou"] for r in grp]
        ars_g = [r["area_ratio"] for r in grp]
        dists_g = [r["dist"] for r in grp]
        print(f"  {cond:<22} n={len(grp):2d}  "
              f"IoU={statistics.mean(ious_g):.3f}  "
              f"area={statistics.mean(ars_g):.3f}  "
              f"dist={statistics.mean(dists_g):.1f}px")


if __name__ == "__main__":
    main()
