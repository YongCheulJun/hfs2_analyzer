# HfS₂ 박막 산화도 분석기 (hfs2_analyzer)

HfS₂ (이황화하프늄) 박막의 자연 산화 정도를 단일 시편 사진만으로 분석·예측하는 Tkinter 데스크톱 앱.

- **메인 파일**: `hfs2_v5_49.py` (단일 파일, ~16,000줄)
- **저장소**: https://github.com/YongCheulJun/hfs2_analyzer (private)
- **Source of truth**: WSL `/home/mystar24/coding/hfs2_analyzer/` (LF 인코딩)
- **Windows 작업본**: `\\wsl$\Ubuntu\home\mystar24\coding\hfs2_analyzer\` (Remote-WSL VSCode 권장)

---

## 빠른 실행 (Windows)

```powershell
cd \\wsl$\Ubuntu\home\mystar24\coding\hfs2_analyzer
pip install -r requirements.txt
python hfs2_v5_49.py
```

---

## 실행 환경

- Windows 네이티브 Python 3.10+ 권장
- 의존성 (`requirements.txt`):
  - `numpy`, `opencv-python`, `Pillow`, `matplotlib`, `tkinterdnd2`, `anthropic`, `scipy>=1.10`
- **Claude API** (AI 분석 탭) — 키는 앱 내 UI 에서 입력. "저장" 체크 시 `%APPDATA%\hfs2_analyzer\settings.json` 평문 보관.
- 한국어 폰트: 맑은 고딕 / NanumGothic / Apple SD Gothic Neo / Noto Sans KR / Gulim / Dotum 중 1개 (`_setup_korean_font` 자동 탐색).
- **WSL 에서 GUI 실행 금지** — 검증은 `python -m py_compile` + 헤드리스 스크립트 (`tools/`) 까지만.

---

## 메인 워크플로

1. **이미지 추가**: 📂 Add 또는 드래그앤드롭으로 시편 사진 일괄 추가 (파일명에서 day/cond 자동 파싱)
2. **▶ Analyze All**: 색상·텍스처 메트릭 + 자동 ROI + 품질 플래그 일괄 계산
3. **(선택) 라만 데이터 추가**: 📡 Raman 탭 → DnD Excel/CSV 또는 수동 입력 → 매칭 picker 로 어느 이미지에 연결할지 선택
4. **(선택) 평가대상 입력**: 🎯 Evaluation 탭 → 추가 → 5-method 앙상블 + Pseudo-Raman 자동 분석
5. **🎯 Optimize Weights** (Advanced 탭): 평가대상 ↔ 분석대상 매칭 ground truth 로 cond 별 ensemble weight 최적화 → settings.json 저장
6. **💾 Save All**: 이미지 + 라만 + 평가대상 + 매칭 정보를 **한 .db 파일**에 통합 저장
7. **📦 Load All**: 통합 .db 파일 한 번에 복원 (단일 파일 또는 다중 파일 자동 감지)
8. **📄 Report**: HTML / DOCX 보고서 (이미지+평가대상+라만 데이터셋 요약, stage 분류, 모든 차트 + 해석)

---

## 핵심 기능

### 이미지 분석
- HSI / Lab / GLCM / Yellowness Index / ΔE 색상·텍스처 메트릭
- KNN / Wasserstein / FFT / Spatial / Kinetic 5가지 추정기 + cond 별 Huber-robust ensemble
- Pseudo-Raman 스펙트럼 재구성 (이미지 메트릭 → A₁ₒ 피크 + 95% CI)
- AI 분석 탭 — Claude API (`claude-sonnet-4-6` + prompt caching)

### ROI 자동 추정 (cond 별 적응)
- HSV V/S 임계 → paper 마스크 → 시편 contour bbox → convex hull 보강 (광택/반사 hole 회복)
- ROI 면적 = **cond 별 학습 비율** (NativeHfS2-35%RH=0.13, NativeHfS2-70%RH=0.15, Al2O3HfS2-70%RH=0.17, PMMA HfS2-70%RH=0.15, default=0.15)
- ROI 중심 = **mass-centroid + bbox 중심 평균** (사용자 의도: 시편 중심부 안전영역)
- 가로/세로 비 = `(시편 bbox AR)^0.5` 정사각형 쪽 완화
- 이미지 가장자리 5% 안쪽 안전 margin
- 품질 플래그: `good` / `warn_paper` / `warn_small` / `warn_off` / `failed`
- `check_roi_group_consistency` — 같은 cond 그룹 IoU < 0.70 outlier PURPLE 마킹 + 옵션 group snap

### 카드 리스트 UI
- 좌측 패널 폭 440px, 카드 썸네일 96×80
- 카드 테두리 색상 코딩:
  - 🟢 GREEN = OK / manual / DB 로드
  - 🟠 AMBER = warn (paper / small / off-edge)
  - 🟣 PURPLE = 같은 cond 그룹 ROI 불일치 (IoU < 0.70)
  - 🔴 RED = 시편 검출 실패
- **⚛ 라만 매칭 뱃지** — `img.raman_id` 가 set 된 카드의 우상단 보라 ⚛
- 품질 우선순위 자동 정렬 (failed → warn → inconsistent → good)
- 선택 클릭 즉시 응답 (PhotoImage 캐시, 두 카드만 in-place 갱신)
- 추가/로드 후 `_sort_images_by_cond_day()` 자동 정렬 (그래프 X축 정렬 보장)
- 헤더 버튼: `🤖 자동 ROI` / `🗑 전체 삭제`

### 다중 이미지 추가 속도 개선
- `_add_images_bulk(items)` — ThreadPoolExecutor (max 8 워커) 로 PIL decode + HSI + auto_detect_roi + make_thumb 병렬 처리
- `_add_image(defer_rebuild=True)` — N장 추가 시 `_rebuild_list` 가 N번 호출되던 O(N²) → 마지막 1회만

### 평가대상 (Evaluation 탭, 최대 20개)
- 카드 리스트 + 자동 ROI + 색상 20색 cycling
- DnD: Evaluation 탭 활성 시 메인 윈도우 드래그앤드롭 → 평가대상 (파일명에서 day/cond 자동 파싱)
- ▶ 모두 분석 — KNN + 5 methods + Ensemble (cond 별 weight 자동 적용) + Pseudo-Raman
- **💾 평가대상 저장** / **📂 평가대상 불러오기** 명시 버튼
- 분석 후 result dict: `{est_day, confidence, target_metrics, scores, top, adv: {knn/wass/fft/spatial/kinetic 각 (day,conf), ens_day, ens_conf, weights, _chart}, stage: {early/mid/late distances, best_stage}, low_time_res, low_time_res_note}`

### 라만 매칭 시스템 (1 라만 ↔ N 이미지)
- 라만 추가 시 `_pick_images_for_raman_dialog` — 체크박스 Treeview, 같은 cond+day 자동 체크, 전체/동일cond/해제 버튼
- 자동 매칭: 라만 데이터 추가/로드 후 `_auto_link_raman_by_cond_day()` 호출 — cond+day 매칭 + raman_id 미배정 이미지에 자동 매핑
- 라만 삭제 시 매칭 자동 해제 (img.raman_id = None) + 카드 ⚛ 뱃지 갱신
- Pseudo-Raman 회귀: `img.raman_id` 우선, cond+day fallback (다중 라만 동일 키 케이스에서 정확한 매칭)

### 통합 DB Save All / Load All
- **한 .db 파일**에 `images` (`raman_id` 컬럼 포함) + `raman_data` + `eval_target` + `meta` 통합
- v1 → v2 자동 ALTER 마이그레이션 (`raman_id` 컬럼 추가)
- **💾 Save All**: tempfile.mkdtemp() local temp 작업 → `shutil.move` (9p / Windows UNC SQLite lock 완전 회피)
- **📦 Load All**: 단일 통합 파일 또는 다중 파일 (.db / .raman.db / .target.db) 자동 감지 → 이미지 + 라만 + 평가대상 + 매칭 모두 한 번에 복원
- 결과 다이얼로그에 이미지/라만/평가대상/매칭 카운트 명시
- LOAD 시 read-only 3단 fallback: ① `file://...?mode=ro` URI ② local temp 복사 ③ plain connect (PRAGMA 변경 없음)
- 분석 안 한 상태에서도 저장 가능 (ROI checkpoint, 메트릭 NULL)

### Advanced Analysis 탭
- 평가대상 Treeview (이름/조건/Day/앙상블/Conf%) — ▶ Run Advanced Estimation 클릭 시 모든 평가대상 분석 → 표 채움 → 첫 행 자동 선택
- Tree 행 선택 시 detail 패널 즉시 갱신:
  - 5 methods StringVar (knn/wass/fft/spatial/kinetic + ensemble)
  - 가중치 바 (cond 별 weight 시각화)
  - 해석 텍스트 (이미지 메타 + Stage 분류 + Al2O3 경고)
  - 차트 3개 (히스토그램/FFT/방사 스펙트럼) 자동 갱신
  - **Stage Similarity 막대 차트** — early/mid/late 정규화 거리 + best_stage ★ 강조
- **🎯 가중치 최적화** 버튼 — 평가대상 ↔ 분석대상 name(또는 cond+day) 매칭 ground truth → leave-one-out → optimize_advanced_weights (Huber loss δ=5d, scipy L-BFGS-B 6 multi-start, scipy 없을 시 11⁵ grid) → cond 별 nested dict 로 settings.json 저장
- Al2O3 등 LOW_TIME_RESOLUTION_CONDS — confidence 30% cap + 노란 경고 (산화 진행 미미로 정확도 본질적 한계)

### 그래프
- Day 축 숫자 정렬 — `xs=[df(p[0]) for p in pts]` 패턴 (string day → float 변환 후 plot). 모든 trend 차트에 일관 적용.
- 5개 차트 (lab_b / delta_e / lab_L / s_trend / yr_trend) + 4개 보충 (h_trend / glcm_con / glcm_eng / 정규화 추이)
- 다중 condition 시 [0,1,2,4,3,7,14] → [0,1,2,3,4,7,14] 정상 정렬

### Estimated Spectrum 차트 해석
- Pseudo-Raman 차트 패널 안에 스크롤 가능한 해석 텍스트 박스 (Consolas 8pt, 12 lines)
- ▶ Run Evaluation 시 `_chart_desc_spectrum(ctx, ko=)` 자동 호출
- 표시: 그래프 개념 / 구성요소 / 추정 4단계 / 결과(Stage I-IV) / 라만 피크 참조값(337/260/500/630 cm⁻¹) / 주의사항

### 보고서 (HTML + DOCX)
- 영문 / 한글 두 파일 동시 생성
- **4. Dataset Summary** — 분석/평가/라만 cond·day·갯수 표
- **5. Image Analysis Data** + 6. Raman + 7. Evaluation Results + **7.1 Evaluation Targets — Detail** (각 평가대상 name/cond/day/ROI/Stage/추정일/신뢰도 표)
- 평가대상별 Stage Similarity 차트 이미지 그리드 (HTML 2열, DOCX 시퀀스)
- 8. Chart Guide / 9. Final Opinion / 10. Advanced / 11. References

---

## 단일 파일 모듈 구조

라인 drift 가 빠르므로 함수 위치는 항상 `grep -n "def 메서드명"` 으로 찾을 것.

| 영역 | 책임 |
|---|---|
| `_setup_korean_font` | matplotlib 한국어 폰트 자동 탐색 |
| `_L`/`set_lang` | 한/영 UI 전환 |
| `parse_filename_tags` | 파일명 → (day, cond) 파싱 |
| `auto_detect_roi`, `_resolve_area_ratio`, `COND_AREA_RATIOS` | cond 별 ROI 자동 추정 |
| `check_roi_group_consistency` | cond 그룹 IoU outlier 마킹 + 옵션 snap |
| `compute_stage_signatures`, `classify_target_stage` | 초기/중기/말기 stage 분류 |
| `LOW_TIME_RESOLUTION_CONDS`, `is_low_time_resolution_cond` | Al2O3 등 신뢰도 가드 |
| HSI / Lab / YI / ΔE 메트릭 | 색상 분석 |
| GLCM / Wasserstein / FFT / Spatial / Kinetic | 텍스처·패턴·동역학 추정기 |
| `adv_ensemble(..., prior_weights=)` | 5-method 앙상블 (flat 또는 cond 별 nested prior) |
| `_resolve_adv_prior(saved, cond)` | settings.json adv_weights 형식 정규화 |
| `optimize_advanced_weights(estimates, huber_delta=5)` | scipy L-BFGS-B 6 multi-start 또는 11⁵ grid fallback |
| `_db_open_safe` (SAVE) / `_db_open_read` (LOAD, 3단 fallback) | SQLite I/O |
| `db_init`, `db_save_all`, `db_load_all`, `db_save_raman_all`, `db_load_raman_all` | 통합 스키마 (raman_id 컬럼) |
| `_db_save` / `_db_save_target` / `_db_save_raman` | tempfile + shutil.move 우회 패턴 |
| `_pred_compute_one(t, with_advanced=True)` | 평가대상 1개 분석 (KNN + advanced + stage + low_time_res) |
| `_compute_advanced_for_target` | 5 methods + ensemble + chart 데이터 보존 |
| `_adv_optimize_weights` | 평가대상 ↔ 분석대상 매칭 LOO 학습 → nested settings 저장 |
| `_adv_run`, `_adv_show_for_target`, `_adv_draw_stage_chart` | Advanced 탭 Treeview + detail + 차트 갱신 |
| `_make_stage_figure(t)` | Stage Similarity figure (Tk + 리포트 PNG 양쪽 재사용) |
| `Settings` (`load_settings`, `save_settings`) | 사용자 설정 영구 저장 |
| `ROISelector` 클래스 | ROI 그리기/이동/복사 다이얼로그 |
| `App` 메인 윈도우 | 거대 단일 클래스. 탭/패널/모든 핸들러 포함 |

---

## 도구 스크립트 (`tools/`)

| 스크립트 | 용도 |
|---|---|
| `extract_pptx_to_db_format.py` | PPTX 슬라이드 → 시편 이미지 추출 + DB 파일명 패턴 자동 생성 |
| `center_crop_images.py` | 이미지 폴더 중앙 크롭 (시편 확대용) |
| `eval_roi.py` | 헤드리스 IoU/면적/중심변위 비교 (수동 ROI vs 자동) |
| `optimize_weights_headless.py` | Tk 없이 advanced ensemble weight 최적화 시뮬 (`--pool` `--targets` `--save`) |

```bash
# Advanced weight 최적화 헤드리스 재현
MPLBACKEND=Agg python3 tools/optimize_weights_headless.py \
    --pool newfiles/output/output_cut/db/alldata.db \
    --targets newfiles/output/output_cut --save
```

---

## 논문 (`paper/`)

- `Jun_HfS2_image_oxidation.docx` — SCIE 논문 영문본 (8 페이지 본문 + Supporting Information 통합, MDPI Applied Sciences 양식)
- `Jun_HfS2_image_oxidation_KO.docx` — 동일 내용 한글 번역본
- `figures/fig1~5.png`, `figS1~S6.png` — 본문 + SI 그림 11장
- `make_paper.py`, `make_paper_ko.py`, `make_figures.py`, `make_si_figures.py` — 재생성 스크립트

저자: 1저자 **Yongcheul Jun (전용철)** (부산대학교 공과대학 지식재산융합전공) / 교신 **Kwangwook Park (박광욱)** (전북대학교 전자정보공학부).

---

## 알려진 함정 / 주의사항

### SQLite lock — 해결됨 (commit 9014776 / 1f05f1e)
- `\\wsl$\` 9p 마운트의 SQLite WAL/lock 충돌 → `db_init` 가 `journal_mode=DELETE` + `_db_save` / `_db_save_target` / `_db_save_raman` 모두 `tempfile.mkdtemp()` local temp 작업 후 `shutil.move`
- LOAD 도 read-only 3단 fallback (`_db_open_read`)
- 잔재 lock 파일 정리:
  ```powershell
  cd \\wsl$\Ubuntu\home\mystar24\coding\hfs2_analyzer\dbfiles
  del *.db-wal, *.db-shm, *.db-journal, *.tmp_save 2>$null
  Get-ChildItem *.db | Where-Object {$_.Length -eq 0} | Remove-Item
  ```

### 단일 거대 파일
- `App` 클래스 ~14,000줄. 라인 drift 빠름.
- 함수/메서드 — symbol grep 으로 찾기.

### 기타
- **TkAgg 백엔드 강제** — `matplotlib.use("TkAgg")`. 다른 백엔드 섞으면 빈 화면.
- **tkinterdnd2 옵셔널** — 미설치 시 `_DND=False` 폴백.
- **scipy 권장** — 없으면 `optimize_advanced_weights` 가 11⁵ grid fallback (같은 결과지만 약 2초 더 느림).
- **Al2O3 cond 한계** — 코팅 보호로 시계열 변화 미미 (r(day, b*) ≈ -0.32 vs 다른 cond -0.83~-0.95). day 추정 정확도 본질적 한계 (RMSE ~8일). UI/리포트에 자동 경고 + confidence 30% 캡.
- **한국어 폰트 미설치** — 그래프 텍스트만 깨짐.

---

## 데이터 폴더 (Git 추적 X)

- `dbfiles/` — `pkw_1.db` (이미지 20장), `raman.raman.db` (라만 20건, Al2O3 만 실제값)
- `newfiles/output/` — `output/` (PNG 33장), `output_cut/` (중앙 크롭 + alldata.db 53장), `sample/` (JPG 20장 평가대상)
- `pkw_papers/` — 참조 논문 PDF
- 모두 `.gitignore`. `paper/` 폴더만 예외 (figure PNG + .docx + .py 추적).

---

## VSCode 작업 환경

**옵션 A — Remote-WSL (권장)**: Windows VSCode 에 "Remote - WSL" 확장 → `code /home/mystar24/coding/hfs2_analyzer`.

**옵션 B — Windows 네이티브 + 동기화**: `sed 's/$/\r/' file.py > /mnt/c/.../file.py` (WSL → Win), `tr -d '\r' < /mnt/c/.../file.py > file.py` (Win → WSL).

---

## 주요 commit 마일스톤 (2026-04-26)

| commit | 내용 |
|---|---|
| `7622b8f` | ROI cond 별 면적 dict + 라만 매칭 시스템 통합 (raman_id, ⚛ 뱃지) |
| `e0ee426` | LOAD lock 회피 read-only + bulk add 속도 개선 |
| `a974798` | `_db_open_read` 3단 fallback (URI / local temp / plain) |
| `ced2c2d` | 이미지 추가/로드 후 cond+day 자동 정렬 |
| `7dcf841` | 평가대상별 advanced + cond 별 weight 학습 |
| `3185a1c` | Advanced 탭 평가대상 Treeview + detail 갱신 |
| `026972d` | 평가대상 선택 시 차트 자동 갱신 |
| `49e7692` | optimize_advanced_weights MSE → Huber loss |
| `3495382` | cond 별 nested adv_weights settings |
| `e9e6c92` | Stage 분류 (early/mid/late) + Al2O3 신뢰도 가드 |
| `1442899` | Stage Similarity 막대 차트 (Advanced 탭) |
| `05446ad` | 리포트에 평가대상별 stage 차트 이미지 포함 |
| `d110a11` | H-ch mean / GLCM 그래프 X축 정렬 버그 수정 |
| `1f05f1e` | Save Targets / Save Raman 9p 우회 적용 |
| `41da694` | Estimated Spectrum 차트 해석 텍스트 박스 |
| `17dbc26` | 툴바 "💾 Save All" / "📦 Load All" 라벨 명확화 |
| `21898a8` | SCIE 논문 (영문/한글) + Supporting Information 통합 |
