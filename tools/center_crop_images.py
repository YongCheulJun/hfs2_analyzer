# -*- coding: utf-8 -*-
"""
이미지 폴더 내 모든 이미지를 중앙 크롭해서 별도 폴더에 저장.

사용법:
    python tools/center_crop_images.py <입력폴더> [<출력폴더>] [<비율>]

기본:
    출력폴더 = <입력폴더>/output_cut
    비율    = 0.55  (가로/세로 각 55% 만 남김 → 약 1.82× 확대)
"""

import os
import sys
from PIL import Image

DEFAULT_RATIO = 0.55
EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")


def center_crop(img: Image.Image, ratio: float) -> Image.Image:
    w, h = img.size
    new_w = int(w * ratio)
    new_h = int(h * ratio)
    left = (w - new_w) // 2
    top = (h - new_h) // 2
    return img.crop((left, top, left + new_w, top + new_h))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    in_dir = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) >= 3 else os.path.join(in_dir, "output_cut")
    ratio = float(sys.argv[3]) if len(sys.argv) >= 4 else DEFAULT_RATIO

    if not (0.1 <= ratio <= 1.0):
        print(f"[ERROR] 비율은 0.1 ~ 1.0 사이여야 함. 받은 값: {ratio}")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    files = sorted(f for f in os.listdir(in_dir)
                   if f.lower().endswith(EXTS) and
                   os.path.isfile(os.path.join(in_dir, f)))
    if not files:
        print(f"[WARN] {in_dir} 에 이미지 없음")
        return

    print(f"[INFO] 입력: {in_dir}  ({len(files)}장)")
    print(f"[INFO] 출력: {out_dir}")
    print(f"[INFO] 비율: {ratio} (각 변 {ratio*100:.0f}% 유지, 면적 ≈ {ratio*ratio*100:.0f}%)")
    print()

    for i, fname in enumerate(files, 1):
        in_path = os.path.join(in_dir, fname)
        out_path = os.path.join(out_dir, fname)
        try:
            with Image.open(in_path) as img:
                cropped = center_crop(img, ratio)
                # 원본 포맷 유지
                save_kwargs = {}
                if fname.lower().endswith((".jpg", ".jpeg")):
                    save_kwargs["quality"] = 95
                cropped.save(out_path, **save_kwargs)
            print(f"  [{i:2d}/{len(files)}] {fname}: {img.size} → {cropped.size}")
        except Exception as e:
            print(f"  [{i:2d}/{len(files)}] {fname}: ERROR - {e}")

    print(f"\n[OK] 완료. {out_dir} 에 {len(files)}장 저장.")


if __name__ == "__main__":
    main()
