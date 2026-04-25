# HfS₂ 박막 산화도 분석기 (hfs2_analyzer)

HfS₂ (이황화하프늄) 박막의 산화 정도를 이미지 기반으로 분석하는 Tkinter 데스크톱 앱.

- **메인 파일**: `hfs2_v5_49.py` (약 14,100줄, 단일 파일)
- **버전 표기**: `HfS₂ 박막 산화도 분석기 v5.0 (1단계 개선)` (코드 docstring 기준)
- **GitHub**: https://github.com/YongCheulJun/hfs2_analyzer (private)
- **Source of truth**: WSL `/home/mystar24/coding/hfs2_analyzer/` (LF 인코딩)
- **Windows 작업본**: `\\wsl$\Ubuntu\home\mystar24\coding\hfs2_analyzer\` (Remote-WSL VSCode 권장)

---

## 빠른 실행 (Windows)

```powershell
# 1. (한 번만) 의존성 설치
cd \\wsl$\Ubuntu\home\mystar24\coding\hfs2_analyzer
pip install -r requirements.txt

# 2. 실행
python hfs2_v5_49.py
```

---

## 실행 환경

- Windows 네이티브 Python 3.10+ 권장
- 의존성 (`requirements.txt`):
  - `numpy`, `opencv-python`, `Pillow`, `matplotlib`, `tkinterdnd2`, `anthropic`
- **Claude API** 사용 시 (AI 분석 탭) — `anthropic-api` 키 필요. 앱 내 UI 에서 입력, "저장" 체크 시 settings.json 에 평문 보관 (`%APPDATA%\hfs2_analyzer\settings.json`).
- 한국어 폰트: 맑은 고딕 / NanumGothic / Apple SD Gothic Neo / Noto Sans KR / Gulim / Dotum 중 1개 (`_setup_korean_font` 자동 탐색).
- **WSL 에서 GUI 실행 금지** — matplotlib TkAgg + Tkinter X11 임베딩 불안정. 코드 검증은 `python -m py_compile` 까지만.

---

## 핵심 기능 (v5 누적)

### 이미지 분석
- HSI / Lab / GLCM / Yellowness Index / ΔE 다중 색상·텍스처 메트릭
- Wasserstein / FFT / Spatial / Kinetic 다중 추정 모델 + 앙상블
- 라만 분광 데이터와 매칭 분석 (cond + day 키)
- AI 분석 탭 — Claude API 호출 (모델: `claude-sonnet-4-6`, prompt caching 적용)

### ROI 자동 추정 (다단계 진화)
- HSV V/S 임계 → paper 마스크 → 시편 bbox 검출
- ROI 면적 = 이미지의 **13%** (DB pkw_1.db 패턴 23.8% 보다 약 45% 작게)
- ROI 중심 = 곡률 가장 큰 변에서 가장 먼 꼭지점 방향 **25%** bias
- 가로/세로 비 = 시편 bbox 비율 자동 적용
- 이미지 가장자리 5% 안쪽 안전 margin
- 품질 플래그: `good` / `warn_paper` / `warn_small` / `warn_off` / `failed`

### 카드 리스트 UI
- **좌측 패널 폭 440px**, 카드 썸네일 96×80
- 카드 테두리 색상 코딩:
  - 🟢 GREEN = OK / manual / DB 로드
  - 🟠 AMBER = warn (paper / small / off-edge)
  - 🟣 PURPLE = 같은 cond 그룹 ROI 불일치 (IoU < 0.70)
  - 🔴 RED = 시편 검출 실패
- **품질 우선순위 자동 정렬** — 문제 카드 위로 (failed → warn_paper → warn_small → warn_off → no-ROI → inconsistent → good)
- **선택 클릭 즉시 응답** — PhotoImage 캐시 + 전체 재빌드 회피, 두 카드만 in-place 갱신
- 헤더 버튼: `🤖 자동 ROI` (manual/DB 보호하고 재추정), `🗑 전체 삭제` (Raman 보존)

### 복수 평가대상 (Evaluation 탭, 최대 8개)
- 카드 리스트 + 자동 ROI + 색상 8색 cycling
- DnD: Evaluation 탭 활성 시 메인 윈도우 드래그앤드롭 → 평가대상으로
- ▶ 모두 분석 — 모든 target 동시 분석, 차트에 ★ 마커 + target color 동시 표시
- DB 마이그레이션 — 기존 단일 row 자동 변환 (백업 테이블 보존)

### DB 저장/로드
- **📂 DB Load**: 이미지 DB 파일 **복수 선택 로드** 지원
- **📦 Load All**: 이미지 / Raman / Target DB 자동 감지 + 일괄 로드
- **🗄 DB Save**: Atomic write 패턴 (`*.tmp_save` → `os.replace`) — lock 회피
- **분석 안 한 상태에서도 저장 가능** (ROI checkpoint) — 메트릭 컬럼 NULL 저장
- DB 로드 시 ROI 보존 + 품질 플래그 자동 평가
- SQLite 모드: **DELETE** (WAL X — 9p 마운트 호환)

### 그래프
- Day 축 숫자 정렬 (다중 condition 시 [0,1,2,4,3,7,14] → [0,1,2,3,4,7,14])
- 5개 차트 (lab_b / delta_e / lab_L / s_mean / yr_trend) 다중 condition 지원

---

## 단일 파일 모듈 구조 (라인 drift 빠름 — symbol 검색 권장)

| 영역 | 책임 |
|---|---|
| `_setup_korean_font` | matplotlib 한국어 폰트 자동 탐색 |
| `_L`/`set_lang` | 한/영 UI 전환 |
| `parse_filename_tags` | 파일명 → (Nday, MRH 조건) 파싱 |
| `auto_detect_roi`, `evaluate_roi_quality` | ROI 자동 추정/품질 평가 |
| `_find_most_curved_side_midpoint`, `_find_corner_far_from_curved_side` | ROI bias 보조 |
| `check_roi_group_consistency` | 같은 cond 그룹 IoU 비교 (PURPLE flag) |
| `_border_color_for_roi`, `_ROI_FLAG_LABEL` | 카드 색상/라벨 매핑 |
| HSI / 황색 메트릭 | RGB→HSI, 황색 비율, YI, S 평균 |
| LAB 메트릭 + ΔE | Lab 공간 통계, 색차 |
| GLCM 텍스처 | 그레이 동시발생 행렬 통계 |
| 히스토그램 + Wasserstein | adv_hist_signature, adv_wasserstein_* |
| FFT 피처 + 추정 | adv_fft_features, adv_fft_estimate |
| 앙상블 | adv_ensemble |
| 공간 피처 + 추정 | adv_spatial_* |
| Kinetic 핏 + 추정 | adv_kinetic_fit, adv_kinetic_estimate |
| `_db_open_safe`, `db_init`, `db_save_all`, `db_load_all` | SQLite I/O (DELETE 모드) |
| `_migrate_eval_target_schema` | 평가대상 테이블 마이그레이션 (백업 보존) |
| `Settings` (settings.py 식 free function) | API 키 등 사용자 설정 영구 저장 |
| `ROISelector` 클래스 | ROI 그리기/이동/복사 다이얼로그 |
| `App` 메인 윈도우 | 거대 단일 클래스 (~12,000줄). 탭/패널/모든 핸들러 포함 |

함수 위치는 `grep -n "def 메서드명"` 으로 찾을 것 — 라인 번호는 commit 마다 변동.

---

## 알려진 함정 / 주의사항

### SQLite 저장 lock — 해결됨 (2026-04-26 commit f2a19aa)
- `\\wsl$\` 9p 마운트에서 SQLite WAL 모드 lock 충돌
- → `db_init` 가 `PRAGMA journal_mode=DELETE` 로 전환됨
- → `_db_save` atomic write (`.tmp_save` → `os.replace`)
- 잔재 lock 파일 정리 (PowerShell):
  ```powershell
  cd \\wsl$\Ubuntu\home\mystar24\coding\hfs2_analyzer\dbfiles
  del *.db-wal, *.db-shm, *.db-journal, *.tmp_save 2>$null
  Get-ChildItem *.db | Where-Object {$_.Length -eq 0} | Remove-Item
  ```

### 단일 거대 파일 (14,100줄)
- `App` 클래스 ~12,000줄. 라인 drift 빠름.
- 함수/메서드 위치 — symbol grep 으로 찾기.
- 큰 리팩토링은 별도 작업으로.

### 기타
- **TkAgg 백엔드 강제** — import 직후 `matplotlib.use("TkAgg")`. 다른 백엔드 섞으면 빈 화면.
- **tkinterdnd2 옵셔널** — 미설치 시 `_DND=False` 폴백. drag-drop 만 비활성화.
- **SQLite blob** — 이미지를 base64 blob 으로 저장. 수백 MB+ 데이터셋에서 느려질 수 있음.
- **한국어 폰트 미설치** — 그래프 텍스트만 깨짐, 앱 동작은 정상.
- **PPTX → PNG 변환 유틸** — `tools/extract_pptx_to_db_format.py`, `tools/center_crop_images.py` 별도 스크립트.

---

## VSCode 작업 환경 (선택)

**옵션 A — Remote-WSL (권장)**: Windows VSCode 에 "Remote - WSL" 확장 설치 → `code /home/mystar24/coding/hfs2_analyzer` → 단일 source of truth.

**옵션 B — Windows 네이티브 + 동기화** (baseballplayer 패턴):
- WSL → Windows: `sed 's/$/\r/' file.py > /mnt/c/.../file.py`
- Windows → WSL: `tr -d '\r' < /mnt/c/.../file.py > file.py`

---

## 데이터 폴더 (Git 추적 X)

- `dbfiles/` — `pkw_1.db` (이미지 20장, ROI 참조 패턴), `raman.raman.db` (Raman 20건, Al2O3 만 실제값)
- `newfiles/` — `HfS2 산화 사진.pptx` (원본), `output/` (PNG 33장), `output_cut/` (중앙 크롭)
- `pkw_papers/` — 사용자 자료
- 모두 `.gitignore` 처리됨

---

## 도구 스크립트 (`tools/`)

| 스크립트 | 용도 |
|---|---|
| `extract_pptx_to_db_format.py` | PPTX 슬라이드 → 시편 이미지 추출 + DB 파일명 패턴(`Nday_MRH_조건명.png`) 자동 생성 |
| `center_crop_images.py` | 이미지 폴더 중앙 크롭 (시편 확대용). 비율 인자로 미세 조정 |

사용 예:
```bash
python3 tools/extract_pptx_to_db_format.py "newfiles/HfS2 산화 사진.pptx"
python3 tools/center_crop_images.py newfiles/output newfiles/output/output_cut 0.45
```

---

## 백로그 / 다음 작업 후보

- 분석 결과 JSON 직렬화 (`result_json` 컬럼 채우기) — 현재 NULL
- 8 target × 분석 시간 진행률 다이얼로그
- 카드 더블클릭 큰 미리보기 팝업
- ROI 색상 변경 명시 다이얼로그 (현재 cycling)
- Pseudo-Raman 다중 target 별도 회귀
- Advanced 탭 다중 target 처리
- README 자동 갱신 (line 번호 drift 자동 추적)
