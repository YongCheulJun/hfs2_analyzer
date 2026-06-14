# 모든 per-condition 수치를 5/4-method × in-sample/nested-LOO 로 재계산해 논문값과 대조
"""폐하 "수치 꼼꼼히" 검증용. estimates 를 /tmp 에 캐시하여 반복 계산 가속.
  MPLBACKEND=Agg python3 tools/verify_numbers.py
"""
from __future__ import annotations
import os, sys, pickle
os.environ.setdefault("MPLBACKEND", "Agg")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tools"))
import numpy as np
from collections import defaultdict
from scipy.optimize import minimize

CACHE = "/tmp/hfs2_est.pkl"
ALL5 = ["knn", "wass", "fft", "spatial", "kinetic"]
M4 = ["knn", "wass", "fft", "spatial"]
HUBER_D = 5.0

def collect():
    from PIL import Image
    from hfs2_v5_49 import (db_load_all, parse_filename_tags, auto_detect_roi, roi_to_mask,
        compute_lab_metrics, compute_s_mean, compute_yellow_ratio, compute_yellowness_index)
    from optimize_weights_headless import compute_methods_for_target, stem
    DB = os.path.join(ROOT, "newfiles/output/output_cut/db/alldata.db")
    SAMPLE = os.path.join(ROOT, "newfiles/output/output_cut")
    pool = db_load_all(DB)
    for im in pool:
        rgb, roi = im.get("rgb"), im.get("roi")
        if rgb is None or roi is None: continue
        if im.get("mask") is None: im["mask"] = roi_to_mask(rgb.shape, roi)
        lab = im.get("lab", {})
        if not lab.get("b") or np.isnan(float(lab.get("b", np.nan))):
            im["lab"] = compute_lab_metrics(rgb, im["mask"]); im["s_mean"] = compute_s_mean(rgb, im["mask"])
            im["yellow_ratio"] = compute_yellow_ratio(rgb, im["mask"]); im["yellowness_idx"] = compute_yellowness_index(rgb, im["mask"])
    ibn = {im.get("name"): im for im in pool}; ibs = {stem(im.get("name","")): im for im in pool}
    est = []
    for fn in sorted(f for f in os.listdir(SAMPLE) if f.lower().endswith((".jpg",".jpeg",".png"))):
        rgb = np.array(Image.open(os.path.join(SAMPLE, fn)).convert("RGB"))
        day_p, cond_p = parse_filename_tags(fn)
        m = ibn.get(fn) or ibs.get(stem(fn))
        if m is None and cond_p and day_p:
            for im in pool:
                if im.get("cond")==cond_p and str(im.get("day",""))==str(day_p): m=im; break
        if m is None: continue
        td = float(m.get("day"))
        roi,_,_ = auto_detect_roi(rgb, cond=cond_p); mask = roi_to_mask(rgb.shape, roi)
        t = {"rgb":rgb,"mask":mask,"roi":roi,"lab":compute_lab_metrics(rgb,mask),"s_mean":compute_s_mean(rgb,mask),
             "yellow_ratio":compute_yellow_ratio(rgb,mask),"yellowness_idx":compute_yellowness_index(rgb,mask),
             "cond":cond_p,"cond_hint":cond_p,"name":fn}
        mr = compute_methods_for_target(t, [im for im in pool if im is not m])
        # mr 값만 추려 picklable 하게
        mrp = {k: (float(v[0]) if v[0] is not None else None, float(v[1])) for k, v in mr.items()}
        est.append((td, mrp, fn, cond_p))
    return est

if os.path.exists(CACHE):
    estimates = pickle.load(open(CACHE, "rb")); print(f"[cache] {len(estimates)} loaded")
else:
    estimates = collect(); pickle.dump(estimates, open(CACHE, "wb")); print(f"[collect] {len(estimates)} cached")

def opt(plain, methods):
    A = np.array([[mr[m][0] if mr[m][0] is not None else np.nan for m in methods] for _, mr in plain], float)
    y = np.array([td for td, _ in plain], float)
    cm = np.nanmean(A, axis=0); cm = np.where(np.isnan(cm), 0.0, cm)
    nm = np.isnan(A)
    if nm.any(): A[np.where(nm)] = np.take(cm, np.where(nm)[1])
    def loss(w):
        w = np.maximum(w, 0.0); s = w.sum()
        if s <= 0: return 1e12
        w = w/s; e = A@w - y; ae = np.abs(e)
        return float(np.mean(np.where(ae<=HUBER_D, 0.5*e*e, HUBER_D*(ae-0.5*HUBER_D))))
    bw = np.ones(len(methods))/len(methods); bl = loss(bw)
    starts = [np.ones(len(methods))/len(methods)] + [np.where(np.arange(len(methods))==i,0.8,0.05) for i in range(len(methods))]
    for x0 in starts:
        r = minimize(loss, x0, bounds=[(0,1)]*len(methods), method="L-BFGS-B")
        if r.fun < bl: bl=r.fun; bw=np.maximum(r.x,0.0)
    return {m: float(bw[i]/bw.sum()) for i, m in enumerate(methods)}

def predict(mr, w, methods):
    vals, ws = [], []
    for m in methods:
        v = mr[m][0]
        if v is not None: vals.append(float(v)); ws.append(w[m])
    if not ws: return None
    ws = np.array(ws)
    return float(np.mean(vals)) if ws.sum()<=0 else float(np.dot(vals, ws/ws.sum()))

def rmse(e):
    e = np.array([x for x in e if x is not None and not np.isnan(x)], float)
    return float(np.sqrt(np.mean(e*e))) if len(e) else float("nan")

plain = [(td, mr) for td, mr, _, _ in estimates]
N = len(estimates)
by = defaultdict(list)
for i,(td,mr,fn,c) in enumerate(estimates): by[c].append(i)
CONDS = ["NativeHfS2-35%RH","NativeHfS2-70%RH","Al2O3HfS2-70%RH","PMMA HfS2-70%RH"]

def cond_uniform(methods, idxs):
    uni = {m:1.0 for m in methods}
    return rmse([predict(estimates[j][1], uni, methods) - estimates[j][0] for j in idxs])
def cond_spec_insample(methods, idxs):
    w = opt([plain[j] for j in idxs], methods) if len(idxs)>=3 else opt(plain, methods)
    return rmse([predict(estimates[j][1], w, methods) - estimates[j][0] for j in idxs])
def cond_spec_loo(methods, idxs):
    el=[]
    for j in idxs:
        others=[k for k in idxs if k!=j]
        w = opt([plain[k] for k in others], methods) if len(others)>=3 else opt(plain, methods)
        el.append(predict(estimates[j][1], w, methods) - estimates[j][0])
    return rmse(el)

print("\n=== 개별 추정기 per-cond RMSE (5-method, descriptor-LOO) ===")
print(f"  {'cond':<20}{'kNN':>7}{'Wass':>7}{'FFT':>7}{'Spat':>7}{'Kin':>7}")
for c in CONDS:
    idxs=by[c]
    vals=[rmse([estimates[j][1][m][0]-estimates[j][0] for j in idxs]) for m in ALL5]
    print(f"  {c:<20}"+"".join(f"{v:>7.2f}" for v in vals))

print("\n=== Ensemble per-cond: uniform / cond-specific ===")
hdr=f"  {'cond':<20}{'uni5':>7}{'uni4':>7}{'cs5_in':>8}{'cs5_LOO':>8}{'cs4_in':>8}{'cs4_LOO':>8}"
print(hdr)
wm = {k:0 for k in ['uni5','uni4','cs5_in','cs5_loo','cs4_in','cs4_loo']}
for c in CONDS:
    idxs=by[c]; n=len(idxs)
    u5=cond_uniform(ALL5,idxs); u4=cond_uniform(M4,idxs)
    c5i=cond_spec_insample(ALL5,idxs); c5l=cond_spec_loo(ALL5,idxs)
    c4i=cond_spec_insample(M4,idxs); c4l=cond_spec_loo(M4,idxs)
    for k,v in zip(wm,[u5,u4,c5i,c5l,c4i,c4l]): wm[k]+=v*n
    print(f"  {c:<20}{u5:>7.2f}{u4:>7.2f}{c5i:>8.2f}{c5l:>8.2f}{c4i:>8.2f}{c4l:>8.2f}")
print(f"  {'weighted-mean':<20}"+"".join(f"{wm[k]/N:>7.2f}" if k=='uni5' else f"{wm[k]/N:>{7 if k=='uni4' else 8}.2f}" for k in ['uni5','uni4','cs5_in','cs5_loo','cs4_in','cs4_loo']))

print("\n=== 전체(global) RMSE ===")
for methods,tag in [(ALL5,'5-method'),(M4,'4-method')]:
    wg=opt(plain,methods)
    gin=rmse([predict(mr,wg,methods)-td for td,mr,_,_ in estimates])
    gl=[]
    for i in range(N):
        w=opt([plain[j] for j in range(N) if j!=i],methods); gl.append(predict(estimates[i][1],w,methods)-estimates[i][0])
    uni={m:1.0 for m in methods}
    u=rmse([predict(mr,uni,methods)-td for td,mr,_,_ in estimates])
    print(f"  {tag}: uniform={u:.2f}  global_in={gin:.2f}  global_LOO={rmse(gl):.2f}")
print("\n  논문 보고값: uniform 7.74 / global 6.30 / cond-specific 4.80 (모두 in-sample, 5-method)")
