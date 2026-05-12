# FPSO Stability & Motion Dashboard

Python 3.13 64-bit 환경에서 SQLite DB에 저장된 FPSO Stability/Motion 계산 결과를
간단히 확인하기 위한 Streamlit 대시보드입니다.

## 왜 Streamlit인가

`pandas`를 이미 써 본 상태라면 Streamlit이 가장 접근하기 쉽습니다.
HTML/CSS/JavaScript를 직접 만들지 않아도 `DataFrame`, 필터, 차트를 Python 코드만으로
바로 화면에 올릴 수 있습니다.

## 설치

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`python` 명령을 인식하지 못하면 Windows Python Launcher를 사용해 보세요.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 샘플 DB 만들기

실제 DB가 아직 없으면 아래 명령으로 샘플 SQLite DB를 만들 수 있습니다.

```powershell
python scripts/create_sample_db.py
```

또는:

```powershell
py -3.13 scripts/create_sample_db.py
```

생성 위치:

```text
data/fpso_results_sample.sqlite
```

## 실행

```powershell
streamlit run app.py
```

`streamlit` 명령이 바로 잡히지 않으면 아래처럼 실행해도 됩니다.

```powershell
python -m streamlit run app.py
```

실행 후 브라우저에서 열리는 화면의 사이드바에서 다음을 선택합니다.

- SQLite DB 업로드 또는 로컬 DB 경로 입력
- DB 안의 테이블 선택
- Loading Condition 필터
- L/B/D 범위 필터
- 확인할 결과 컬럼(GM, Max.SF, Roll Tn 등)

## DB 형태

현재 앱은 아래처럼 한 행에 한 계산 케이스가 저장된 형태를 가정합니다.

| L | B | D | T | LC | GM | Max.SF | Max.BM | Heave Tn | Roll Tn | Pitch Tn | Heave MPM |
|---|---|---|---|----|----|--------|--------|----------|---------|----------|-----------|
| 335 | 65 | 32 | 12 | FullLoad | 5.1 | 2200 | 7400 | 1.8 | 28.5 | 14.2 | 1.1 |

필수에 가까운 컬럼:

- `L`, `B`, `D`: 제원별 탭을 만들기 위한 컬럼
- `LC`: Loading Condition 필터용 컬럼
- 그 외 숫자 컬럼: 차트의 Y축 결과값

`LC` 대신 `Loading Condition`, `LoadingCondition`, `Load Condition`, `Condition`도 자동 인식합니다.

## 코드 구조

- `app.py`: Streamlit 화면 구성
- `src/db.py`: SQLite 연결, 테이블 목록 조회, 테이블 로딩
- `src/data_utils.py`: 컬럼 정리, 숫자 변환, 필터, 요약표
- `src/charts.py`: Plotly 차트 생성
- `src/config.py`: 기본 경로와 자주 쓰는 컬럼명 설정
- `scripts/create_sample_db.py`: 테스트용 샘플 DB 생성

처음 수정할 때는 보통 `src/config.py`에서 컬럼 후보를 바꾸거나,
`app.py`의 사이드바/탭 구성을 조금 고치면 됩니다.
