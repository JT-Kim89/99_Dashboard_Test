"""Dashboard-wide settings.

이 파일은 앱 전체에서 공통으로 쓰는 값만 모아 둡니다.
나중에 기본 DB 위치나 자주 쓰는 컬럼 이름을 바꾸고 싶으면
대부분 이 파일만 먼저 보면 됩니다.
"""

from pathlib import Path


# 프로젝트 루트 폴더입니다. app.py, requirements.txt가 있는 위치를 뜻합니다.
BASE_DIR = Path(__file__).resolve().parent.parent

# 샘플 DB 위치입니다. 실제 DB가 없을 때 앱을 바로 테스트할 수 있게 둡니다.
DEFAULT_DB_PATH = BASE_DIR / "data" / "fpso_results_sample.sqlite"

# Streamlit 파일 업로드를 잠시 저장할 폴더입니다.
UPLOAD_DIR = BASE_DIR / ".streamlit_uploads"

# 사용자가 말한 주요 제원 컬럼입니다.
# DB 컬럼명이 정확히 L, B, D이면 앱이 자동으로 이 컬럼들을 탭으로 보여줍니다.
DEFAULT_DIMENSION_COLUMNS = ["L", "B", "D"]

# Loading Condition 컬럼은 회사/프로그램마다 이름이 조금 다를 수 있어서
# 자주 나오는 후보 이름을 여러 개 둡니다.
CONDITION_COLUMN_CANDIDATES = [
    "LC",
    "Loading Condition",
    "LoadingCondition",
    "Load Condition",
    "Condition",
]
