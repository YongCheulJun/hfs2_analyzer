# HfS₂ 박막 산화도 분석기 (hfs2_analyzer)

HfS₂ (이황화하프늄) 박막의 산화 정도를 이미지 기반으로 분석하는 Tkinter 데스크톱 앱.

- 메인 파일: `hfs2_v5_49.py` (12,369줄, 단일 파일)
- 버전 표기: `HfS₂ 박막 산화도 분석기 v5.0 (1단계 개선)`
- 원본 위치: `C:\Users\USER\Downloads\hfs2_v5_49.py` (Windows VSCode 작업 본)
- 이 repo: WSL 의 source of truth (LF 인코딩)

---

## 실행 환경

- Windows 네이티브 Python 3.10+ 권장
- 의존성: `pip install -r requirements.txt`
  - numpy, opencv-python, Pillow, matplotlib, tkinterdnd2
- 한국어 폰트: 맑은 고딕 / NanumGothic / Apple SD Gothic Neo / Noto Sans KR / Gulim / Dotum 중 1개 설치되어 있어야 그래프 한글 정상 표기 (`_setup_korean_font` 가 자동 탐색)
- **WSL 에서 GUI 실행 금지** — matplotlib TkAgg + Tkinter X11 임베딩이 WSL 환경에서 안정적이지 않음. 코드 검증은 `python -m py_compile` 까지만.
- 실제 실행/테스트는 사용자가 Windows 에서.

---

## 모듈 구조 (단일 파일 내 섹션)

| 섹션 | 라인 | 책임 |
|---|---|---|
| 한글 폰트 셋업 | 29~51 | matplotlib 한국어 폰트 자동 탐색 |
| 언어 전환 (`_L`/`set_lang`) | 53~59 | 한/영 UI 전환 |
| `parse_filename_tags` | 101~ | 파일명 → (Nday, MRH 조건) 파싱 |
| HSI / 황색 메트릭 | 146~213 | RGB→HSI, 황색 비율, Yellowness Index, S 평균 |
| LAB 메트릭 + ΔE | 220~256 | Lab 공간 통계, 색차 계산 |
| GLCM 텍스처 | 259~298 | 그레이 동시발생 행렬 통계 |
| 통합 메트릭 (`compute_all_metrics`) | 300~ | 위 메트릭 일괄 계산 |
| ROI → mask | 326~360 | seg_stats, roi_to_mask |
| 히스토그램 시그니처 + Wasserstein | 367~436 | adv_hist_signature, adv_wasserstein_* |
| FFT 피처 + 추정 | 439~559 | adv_fft_features, adv_fft_estimate |
| 앙상블 | 562~600 | adv_ensemble |
| 공간 피처 + 추정 | 605~740 | adv_spatial_* |
| Kinetic 핏 + 추정 | 746~915 | adv_kinetic_fit, adv_kinetic_estimate |
| Pool 사전계산 | 917~937 | adv_precompute_pool |
| 썸네일 / 드롭 파싱 | 939~960 | make_thumb, parse_drop_paths |
| SQLite DB I/O | 968~1126 | db_init, db_save_all, db_load_all (이미지를 base64 blob 으로 저장) |
| `ROISelector` 클래스 | 1129~1444 | ROI 그리기/이동/복사 다이얼로그 |
| `App` 메인 윈도우 | 1459~12367 | 거대 단일 클래스. 탭/패널/모든 핸들러 포함 |

---

## 주요 기능 (v5.0 개선사항)

1. 파일명 파싱 — `Nday_MRH_조건명` 완전 지원
2. 황색 잔존 비율 — H 채널 → 실제 각도 변환 후 비교 (수정)
3. H/S/I 채널 그래프 1탭 통합 + 더블클릭 확대
4. ROI 복사 + 드래그 이동 (신규 ROI 그리기 유지)
5. 라이트 테마 (흰색 계통)
6. Wasserstein / FFT / Spatial / Kinetic 다중 추정 모델 + 앙상블

---

## VSCode 작업 환경 옵션

### 옵션 A — VSCode Remote-WSL (권장)
1. Windows VSCode 에 "Remote - WSL" 확장 설치
2. WSL 안에서 `code /home/mystar24/coding/hfs2_analyzer` 실행
3. WSL 셸을 그대로 VSCode 가 열어줌 → 파일 동기화 불필요

### 옵션 B — Windows 네이티브 VSCode + WSL 동기화 (baseballplayer 패턴)
- WSL 에서 수정 시 Windows 측으로 push:
  ```
  sed 's/$/\r/' /home/mystar24/coding/hfs2_analyzer/hfs2_v5_49.py > /mnt/c/Users/USER/Downloads/hfs2_v5_49.py
  ```
- Windows 에서 수정 시 WSL 측으로 pull:
  ```
  tr -d '\r' < /mnt/c/Users/USER/Downloads/hfs2_v5_49.py > /home/mystar24/coding/hfs2_analyzer/hfs2_v5_49.py
  ```
- 어느 쪽이 source of truth 인지 항상 의식할 것 (WSL 권장).

---

## 알려진 함정 / 주의사항

- **단일 12,369줄 파일** — `App` 클래스 하나만 약 11,000줄. 함수/메서드 위치는 라인 번호 대신 symbol 검색(`grep -n "def 메서드명"`)으로 찾을 것. 리팩토링 큰 위험.
- **TkAgg 백엔드 강제** — `matplotlib.use("TkAgg")` 가 import 직후 호출됨. 다른 백엔드와 섞으면 빈 화면.
- **tkinterdnd2 옵셔널** — 미설치 시 `_DND=False` 로 폴백. drag-drop 만 비활성화되고 앱은 정상.
- **SQLite DB** — 이미지를 base64 blob 으로 저장. 큰 데이터셋 (수백 MB+) 에서 느려질 수 있음.
- **한국어 폰트 미설치** — 그래프 텍스트만 깨짐, 앱 동작은 정상.

---

## TODO / 백로그 (사용자가 채워나갈 영역)

(작업 재개 시 여기 채워가기)
