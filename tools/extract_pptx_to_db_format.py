# -*- coding: utf-8 -*-
"""
PPTX 안의 시편 이미지들을 추출해 DB 파일명 패턴(<day>day_<RH>RH_<COMP>.png)으로 저장.

사용법:
    python tools/extract_pptx_to_db_format.py <pptx_path> [<output_dir>]

기본 출력 폴더: <pptx_의_부모>/output/
이미지·day 라벨 매칭은 슬라이드 XML 내부 좌표(EMU)를 이용한 최근접 거리 매칭.
슬라이드 제목 텍스트에서 composition/RH 자동 판정 (Native / PMMA / Al2O3).
"""

import collections
import os
import posixpath
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


def slide_title_text(spTree):
    for sp in spTree.findall(".//p:sp", NS):
        text = " ".join((t.text or "") for t in sp.findall(".//a:t", NS))
        if "RH)" in text or "% RH" in text:
            return text
    return ""


def parse_title_to_meta(title: str) -> tuple[str, str]:
    """제목 → (composition_for_filename, rh_str)"""
    m_rh = re.search(r"(\d+)\s*%?\s*RH", title)
    rh = m_rh.group(1) if m_rh else "70"
    if "PMMA" in title:
        comp = "PMMA_HFS2"
    elif re.search(r"Al\s*2\s*O\s*3", title):
        comp = "Al2O3HFS2"
    else:
        comp = "NativeHFS2"
    return comp, rh


def extract_pics_and_labels(spTree):
    pics = []   # (x, y, cx, cy, rId)
    labels = [] # (x, y, day_int, full_text)
    for child in spTree:
        tag = child.tag.split("}")[-1]
        if tag == "pic":
            xfrm = child.find(".//p:spPr/a:xfrm/a:off", NS)
            ext = child.find(".//p:spPr/a:xfrm/a:ext", NS)
            blip = child.find(".//p:blipFill/a:blip", NS)
            if xfrm is None or ext is None or blip is None:
                continue
            rid = blip.get(R_EMBED)
            if rid is None:
                continue
            pics.append((int(xfrm.get("x")), int(xfrm.get("y")),
                         int(ext.get("cx")), int(ext.get("cy")), rid))
        elif tag == "sp":
            xfrm = child.find(".//p:spPr/a:xfrm/a:off", NS)
            if xfrm is None:
                continue
            text = " ".join((t.text or "") for t in child.findall(".//a:t", NS))
            m = re.search(r"(\d+)\s*day", text, re.IGNORECASE)
            if m and "RH" not in text:
                labels.append((int(xfrm.get("x")), int(xfrm.get("y")),
                               int(m.group(1)), text.strip()))
    return pics, labels


def match_pic_to_day(pic, labels):
    """PIC 중심점에서 가장 가까운 day-label SP 찾기"""
    px = pic[0] + pic[2] // 2
    py = pic[1] + pic[3] // 2
    best = None
    best_d = float("inf")
    for lx, ly, day, text in labels:
        # SP 박스의 중심 추정 (텍스트 길이에 무관하게 라벨 시작점 + 작은 offset)
        cx = lx + 200000
        cy = ly + 100000
        d = (px - cx) ** 2 + (py - cy) ** 2
        if d < best_d:
            best_d = d
            best = (day, text)
    return best


def load_rels(z: zipfile.ZipFile, slide_path: str) -> dict:
    """slide N 의 rId → media path 매핑 (zip 내부 absolute path)"""
    rels_path = slide_path.replace("slides/slide", "slides/_rels/slide") + ".rels"
    rels_root = ET.fromstring(z.read(rels_path))
    out = {}
    for rel in rels_root:
        rid = rel.get("Id")
        target = rel.get("Target", "")
        # 상대경로(../media/...) → zip absolute path(ppt/media/...)
        abs_path = posixpath.normpath(posixpath.join("ppt/slides", target))
        out[rid] = abs_path
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    pptx_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) >= 3 else os.path.join(
        os.path.dirname(os.path.abspath(pptx_path)), "output")
    os.makedirs(out_dir, exist_ok=True)

    counter = collections.Counter()
    skipped = []
    rows = []

    with zipfile.ZipFile(pptx_path) as z:
        slide_names = sorted(n for n in z.namelist()
                             if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
        print(f"[INFO] PPTX: {pptx_path}")
        print(f"[INFO] 슬라이드 {len(slide_names)}장 분석 시작\n")

        for sname in slide_names:
            root = ET.fromstring(z.read(sname))
            spTree = root.find(".//p:cSld/p:spTree", NS)
            if spTree is None:
                continue
            title = slide_title_text(spTree)
            comp, rh = parse_title_to_meta(title)
            pics, labels = extract_pics_and_labels(spTree)
            rels = load_rels(z, sname)

            slide_no = re.search(r"slide(\d+)", sname).group(1)
            print(f"  [slide {slide_no}] title={title!r}")
            print(f"               → comp={comp}  rh={rh}  pics={len(pics)}  day_labels={len(labels)}")

            for pic in pics:
                rid = pic[4]
                media_path = rels.get(rid)
                if not media_path:
                    skipped.append((sname, rid, "rels miss"))
                    continue
                # 우선 PNG/JPG/JPEG 만, 그 외는 .wdp 등이라 스킵
                ext = os.path.splitext(media_path)[1].lower()
                if ext not in (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"):
                    skipped.append((sname, rid, f"unsupported ext: {ext}"))
                    continue
                if not labels:
                    skipped.append((sname, rid, "no day labels"))
                    continue
                day, label_text = match_pic_to_day(pic, labels)
                base = f"{day}day_{rh}RH_{comp}"
                counter[base] += 1
                suffix = "" if counter[base] == 1 else f"_v{counter[base]}"
                out_name = f"{base}{suffix}{ext}"
                out_path = os.path.join(out_dir, out_name)
                with open(out_path, "wb") as f:
                    f.write(z.read(media_path))
                rows.append((slide_no, rid, label_text, media_path, out_name))

    print(f"\n[OK] 총 {len(rows)} 파일 생성 → {out_dir}/")
    print("\n=== 매핑 결과 ===")
    for slide_no, rid, label, media, out in rows:
        print(f"  slide{slide_no} {rid}  ({media})  ← {label!r}\n        → {out}")
    if skipped:
        print(f"\n[SKIP] {len(skipped)} 항목 스킵:")
        for s, r, why in skipped:
            print(f"  {s} {r}: {why}")


if __name__ == "__main__":
    main()
