"""Analysis helpers for the FPSO dashboard.

이 파일은 화면(Streamlit)과 직접 관련 없는 "계산/판단 로직"을 모아 둔 곳입니다.

초보자용 큰 그림:
- app.py는 버튼, 탭, 표, 그래프 배치 같은 화면 일을 합니다.
- 이 파일은 DataFrame을 받아서 "어떤 컬럼이 L/B/D인가?", "어떤 테이블이 RAO인가?",
  "R2는 얼마인가?", "Pareto set은 무엇인가?" 같은 분석 일을 합니다.

이렇게 나누는 이유:
- 화면 코드와 계산 코드가 섞이면 나중에 수정하기 어려워집니다.
- 분석 함수는 Streamlit 없이도 단독 테스트가 가능합니다.
- 실제 DB 컬럼명이 조금 달라져도 이 파일의 후보 리스트만 고치면 되는 경우가 많습니다.
"""

from __future__ import annotations

from collections.abc import Iterable
from itertools import combinations
import math
import re

import numpy as np
import pandas as pd

from src.config import CONDITION_COLUMN_CANDIDATES, DEFAULT_DIMENSION_COLUMNS
from src.data_utils import find_first_existing_column, get_existing_columns


# 사용자가 Individual Plots 탭에서 선택하는 결과 종류입니다.
# 실제 DB 테이블명이 정확히 이 이름이 아니어도 아래 KEYWORDS로 비슷하게 찾아봅니다.
RESULT_TYPES = ["SF", "BM", "GZ", "RAO", "ShortTerm MPM"]

# case를 구분할 때 L/B/D/LC 외에 같이 표시하면 좋은 컬럼 후보입니다.
# 예를 들어 같은 L/B/D/LC라도 draft(T)가 다르면 다른 case로 보는 편이 안전합니다.
CASE_EXTRA_COLUMN_CANDIDATES = [
    "T",
    "Draft",
    "Draught",
]

# 최적제원 탭에서 "경제성"의 기본 objective로 삼을 컬럼 후보입니다.
# 실제 DB에서는 컬럼명이 Hull Steel Weight, SteelWeight 등으로 다를 수 있으므로
# 자주 쓸 만한 이름을 여러 개 둡니다.
HULL_WEIGHT_COLUMN_CANDIDATES = [
    "Hull Steel Weight",
    "HullSteelWeight",
    "Hull Steel Wt",
    "Steel Weight",
    "SteelWeight",
    "Hull Weight",
]

# 축(axis)으로 쓰일 가능성이 큰 컬럼명 키워드입니다.
# 예: SF/BM의 길이방향 위치 X, GZ의 heel angle, RAO의 frequency/heading 등.
# 이런 컬럼은 "결과값"이 아니라 그래프의 x축/조건으로 쓰이므로 metric 후보에서 제외합니다.
AXIS_COLUMN_KEYWORDS = [
    "x",
    "station",
    "position",
    "longitudinal",
    "length distribution",
    "heel",
    "angle",
    "frequency",
    "freq",
    "omega",
    "period",
    "heading",
    "hdg",
]

# 테이블명 또는 컬럼명에 포함되면 해당 결과 타입으로 추정할 키워드입니다.
# 예: 컬럼 중 Max.SF가 있으면 SF 관련 결과가 있다고 추정합니다.
RESULT_TYPE_KEYWORDS = {
    "SF": ["sf", "shear"],
    "BM": ["bm", "bending"],
    "GZ": ["gz", "righting", "heel"],
    "RAO": ["rao", "response amplitude"],
    "ShortTerm MPM": ["mpm", "shortterm", "short term", "tn33", "tn44", "tn55"],
}

# 결과 타입별로 x축을 찾을 때 우선으로 볼 키워드입니다.
# SF/BM은 길이방향 위치, GZ는 경사각, RAO는 주파수 계열 컬럼이 x축입니다.
X_AXIS_KEYWORDS = {
    "SF": ["x", "station", "position", "longitudinal", "length distribution"],
    "BM": ["x", "station", "position", "longitudinal", "length distribution"],
    "GZ": ["heel", "angle", "inclination"],
    "RAO": ["frequency", "freq", "omega", "period"],
    "ShortTerm MPM": [],
}

# RAO는 heading별로 결과가 분리되는 경우가 많아서 heading 컬럼 후보를 따로 둡니다.
HEADING_KEYWORDS = ["heading", "hdg", "wave heading"]

# RAO 6자유도 motion 결과 컬럼을 찾기 위한 후보입니다.
DOF_KEYWORDS = ["surge", "sway", "heave", "roll", "pitch", "yaw"]


def normalize_text(value: object) -> str:
    """Return a simple lowercase token used for fuzzy column/table matching.

    예:
    - "Hull Steel Weight" -> "hullsteelweight"
    - "Max.SF" -> "maxsf"

    공백, 점, 언더스코어 같은 차이를 없애면 컬럼명 자동 인식이 쉬워집니다.
    """

    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def contains_any_keyword(value: object, keywords: Iterable[str]) -> bool:
    """Check whether value contains any keyword after light normalization.

    주의:
    - "x"는 너무 짧은 키워드라서 Max.SF 안의 x까지 잘못 잡을 수 있습니다.
    - 그래서 x는 x, xpos, xposition 같은 명확한 축 이름일 때만 매칭합니다.
    """

    normalized_value = normalize_text(value)
    for keyword in keywords:
        normalized_keyword = normalize_text(keyword)
        if normalized_keyword == "x":
            if normalized_value in {"x", "xpos", "xposition", "xcoordinate"}:
                return True
            continue
        if normalized_keyword in normalized_value:
            return True
    return False


def find_columns_by_keywords(columns: Iterable[str], keywords: Iterable[str]) -> list[str]:
    """Return columns whose names contain at least one keyword."""

    return [column for column in columns if contains_any_keyword(column, keywords)]


def get_dimension_columns(df: pd.DataFrame) -> list[str]:
    """Find the available L/B/D columns in a table."""

    return get_existing_columns(df.columns, DEFAULT_DIMENSION_COLUMNS)


def get_condition_column(df: pd.DataFrame) -> str | None:
    """Find the loading-condition column in a table."""

    return find_first_existing_column(df.columns, CONDITION_COLUMN_CANDIDATES)


def get_case_columns(df: pd.DataFrame) -> list[str]:
    """Return columns that identify a design/loading case.

    case를 식별하는 컬럼은 보통 다음과 같습니다.
    - L, B, D: 제원
    - LC: Loading Condition
    - T/Draft: 흘수 조건

    이 컬럼들을 묶으면 "하나의 설계/하중 조건 case"를 설명할 수 있습니다.
    """

    case_columns = get_dimension_columns(df)
    condition_column = get_condition_column(df)
    if condition_column is not None:
        case_columns.append(condition_column)

    case_columns.extend(get_existing_columns(df.columns, CASE_EXTRA_COLUMN_CANDIDATES))
    return list(dict.fromkeys(case_columns))


def get_case_hover_columns(df: pd.DataFrame) -> list[str]:
    """Return compact hover columns requested by the user."""

    hover_columns = get_dimension_columns(df)
    condition_column = get_condition_column(df)
    if condition_column is not None:
        hover_columns.append(condition_column)
    return hover_columns


def is_axis_like_column(column: str) -> bool:
    """Decide whether a numeric column is an axis/context field, not a result."""

    normalized_column = normalize_text(column)
    for keyword in AXIS_COLUMN_KEYWORDS:
        normalized_keyword = normalize_text(keyword)
        if normalized_keyword == "x":
            if normalized_column in {"x", "xpos", "xposition", "xcoordinate"}:
                return True
            continue
        if normalized_keyword in normalized_column:
            return True
    return False


def get_numeric_result_columns(
    df: pd.DataFrame,
    exclude_columns: Iterable[str] = (),
    exclude_axis_columns: bool = True,
) -> list[str]:
    """Return numeric columns that are likely to be output/result values.

    pandas에서 숫자 컬럼이라고 해서 모두 결과값은 아닙니다.
    예:
    - L/B/D/T는 숫자지만 case 설명 컬럼입니다.
    - Frequency/Heading/Angle은 숫자지만 x축 또는 조건 컬럼입니다.
    - GM, Max.SF, Max.BM, Roll MPM 등은 실제 output metric입니다.

    그래서 exclude_columns와 axis-like 판정을 함께 써서 결과 컬럼만 남깁니다.
    """

    excluded = set(exclude_columns)
    numeric_columns = df.select_dtypes(include="number").columns
    result_columns = []

    for column in numeric_columns:
        if column in excluded:
            continue
        if exclude_axis_columns and is_axis_like_column(column):
            continue
        result_columns.append(column)

    return result_columns


def classify_table(table_name: str, df: pd.DataFrame) -> list[str]:
    """Classify a table as SF/BM/GZ/RAO/ShortTerm MPM using its name and columns.

    실제 DB 테이블명이 정확히 "RAO"가 아닐 수 있습니다.
    예를 들어 "motion_rao_result", "RAO_Result", "response_amplitude"처럼
    저장될 수 있습니다.

    그래서 테이블명과 컬럼명을 모두 한 문자열로 합친 뒤 키워드로 추정합니다.
    """

    searchable_text = " ".join([table_name, *map(str, df.columns)])
    matches = []
    for result_type, keywords in RESULT_TYPE_KEYWORDS.items():
        if contains_any_keyword(searchable_text, keywords):
            matches.append(result_type)
    return matches


def build_table_profiles(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build a compact profile table for all loaded DB tables."""

    rows = []
    for table_name, df in tables.items():
        dimension_columns = get_dimension_columns(df)
        condition_column = get_condition_column(df)
        case_columns = get_case_columns(df)
        result_columns = get_numeric_result_columns(df, exclude_columns=case_columns)
        classifications = classify_table(table_name, df)

        rows.append(
            {
                "Table": table_name,
                "Rows": len(df),
                "Columns": len(df.columns),
                "Dimensions": ", ".join(dimension_columns) or "-",
                "LC Column": condition_column or "-",
                "Result Types": ", ".join(classifications) or "General",
                "Numeric Results": len(result_columns),
            }
        )

    return pd.DataFrame(rows)


def calculate_missing_ratio(df: pd.DataFrame) -> float:
    """Return the ratio of missing cells in the table."""

    total_cells = df.shape[0] * df.shape[1]
    if total_cells == 0:
        return 0.0
    return float(df.isna().sum().sum() / total_cells)


def count_duplicate_cases(df: pd.DataFrame) -> int:
    """Count duplicate design/loading cases using available case columns."""

    case_columns = get_case_columns(df)
    if not case_columns:
        return 0
    return int(df.duplicated(subset=case_columns).sum())


def build_data_quality_report(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build a high-signal quality report for all loaded tables.

    실제 C# 해석 결과 DB를 처음 연결하면 가장 먼저 확인할 부분입니다.
    - Missing Cell %: 빈 값이 많은지
    - Duplicate Cases: 같은 L/B/D/LC/T 조합이 중복 저장되었는지
    - Dimensions Missing: L/B/D 컬럼 중 빠진 것이 있는지
    - Numeric Results: 차트/분석에 쓸 수 있는 숫자 output이 있는지
    """

    rows = []
    for table_name, df in tables.items():
        dimension_columns = get_dimension_columns(df)
        condition_column = get_condition_column(df)
        case_columns = get_case_columns(df)
        result_columns = get_numeric_result_columns(df, exclude_columns=case_columns)
        missing_dimensions = [
            column for column in DEFAULT_DIMENSION_COLUMNS if column not in df.columns
        ]

        rows.append(
            {
                "Table": table_name,
                "Rows": len(df),
                "Columns": len(df.columns),
                "Missing Cell %": round(calculate_missing_ratio(df) * 100.0, 2),
                "Duplicate Cases": count_duplicate_cases(df),
                "Dimensions Found": ", ".join(dimension_columns) or "-",
                "Dimensions Missing": ", ".join(missing_dimensions) or "-",
                "LC Column": condition_column or "-",
                "Numeric Results": len(result_columns),
            }
        )

    return pd.DataFrame(rows)


def build_case_coverage_table(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize how many rows exist for each L/B/D and loading-condition group."""

    group_columns = get_dimension_columns(df)
    condition_column = get_condition_column(df)
    if condition_column is not None:
        group_columns.append(condition_column)

    if not group_columns:
        return pd.DataFrame()

    coverage = (
        df.groupby(group_columns, dropna=False)
        .size()
        .reset_index(name="Row Count")
        .sort_values(group_columns)
        .reset_index(drop=True)
    )
    return coverage


def get_tables_with_dimensions(tables: dict[str, pd.DataFrame]) -> list[str]:
    """Return tables that contain at least one L/B/D dimension column."""

    return [
        table_name
        for table_name, df in tables.items()
        if len(get_dimension_columns(df)) > 0
    ]


def choose_default_summary_table(tables: dict[str, pd.DataFrame]) -> str:
    """Choose the table with dimensions and the most numeric result columns.

    Summary 탭의 기본 테이블을 자동으로 고르는 간단한 기준입니다.
    - L/B/D가 있는 테이블에 큰 점수를 줍니다.
    - 결과 숫자 컬럼이 많은 테이블을 선호합니다.

    실제 프로젝트에서는 사용자가 사이드바에서 직접 바꿀 수 있으므로,
    이 함수는 어디까지나 첫 선택을 편하게 해 주는 역할입니다.
    """

    scored_tables = []
    for table_name, df in tables.items():
        case_columns = get_case_columns(df)
        result_columns = get_numeric_result_columns(df, exclude_columns=case_columns)
        dimension_score = len(get_dimension_columns(df)) * 100
        scored_tables.append((dimension_score + len(result_columns), table_name))

    if not scored_tables:
        return next(iter(tables))

    return max(scored_tables)[1]


def format_case_value(value: object) -> str:
    """Format one value in a compact case label."""

    if pd.isna(value):
        return "-"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def make_case_label(row: pd.Series, case_columns: list[str]) -> str:
    """Create a readable case label like 'L=335 | B=65 | D=32 | LC=FullLoad'.

    DataFrame 내부에서는 행 index만으로 case를 구분할 수 있지만,
    사용자가 화면에서 비교하려면 사람이 읽을 수 있는 이름이 필요합니다.
    이 함수가 그 표시용 이름을 만듭니다.
    """

    if not case_columns:
        return f"Row {row.name}"
    return " | ".join(
        f"{column}={format_case_value(row[column])}"
        for column in case_columns
        if column in row.index
    )


def add_case_label(df: pd.DataFrame, case_columns: list[str]) -> pd.DataFrame:
    """Add a Case column without mutating the original DataFrame."""

    labeled = df.copy()
    labeled["Case"] = labeled.apply(make_case_label, axis=1, case_columns=case_columns)
    return labeled


def get_unique_cases(df: pd.DataFrame, case_columns: list[str]) -> pd.DataFrame:
    """Return one row per unique case, including a readable Case label."""

    if not case_columns:
        case_df = pd.DataFrame({"Case": [f"Row {index}" for index in df.index]})
        case_df["_source_index"] = list(df.index)
        return case_df

    existing_case_columns = [column for column in case_columns if column in df.columns]
    case_df = df[existing_case_columns].drop_duplicates().reset_index(drop=True)
    case_df = add_case_label(case_df, existing_case_columns)
    return case_df


def filter_by_case_labels(
    df: pd.DataFrame,
    case_columns: list[str],
    selected_case_labels: list[str],
) -> pd.DataFrame:
    """Keep rows whose computed case label is selected."""

    if not selected_case_labels:
        return df.iloc[0:0].copy()

    labeled = add_case_label(df, case_columns)
    return labeled[labeled["Case"].isin(selected_case_labels)].copy()


def find_axis_column(df: pd.DataFrame, result_type: str) -> str | None:
    """Find the best x-axis column for SF/BM/GZ/RAO tables."""

    keywords = X_AXIS_KEYWORDS.get(result_type, [])
    matches = find_columns_by_keywords(df.columns, keywords)
    numeric_matches = [
        column for column in matches if pd.api.types.is_numeric_dtype(df[column])
    ]
    return numeric_matches[0] if numeric_matches else None


def find_heading_column(df: pd.DataFrame) -> str | None:
    """Find a heading column in an RAO table."""

    matches = find_columns_by_keywords(df.columns, HEADING_KEYWORDS)
    return matches[0] if matches else None


def find_default_result_column(df: pd.DataFrame, result_type: str) -> str | None:
    """Find a default y-axis/result column for a result type."""

    case_columns = get_case_columns(df)
    axis_column = find_axis_column(df, result_type)
    heading_column = find_heading_column(df) if result_type == "RAO" else None
    exclude_columns = [*case_columns, axis_column, heading_column]
    result_columns = get_numeric_result_columns(
        df,
        exclude_columns=[column for column in exclude_columns if column is not None],
        exclude_axis_columns=True,
    )

    keyword_matches = [
        column
        for column in result_columns
        if contains_any_keyword(column, RESULT_TYPE_KEYWORDS.get(result_type, []))
        or (result_type == "RAO" and contains_any_keyword(column, DOF_KEYWORDS))
    ]

    if keyword_matches:
        return keyword_matches[0]
    return result_columns[0] if result_columns else None


def get_result_type_table_options(
    tables: dict[str, pd.DataFrame],
    result_type: str,
) -> list[str]:
    """Return table names that look relevant for the selected result type."""

    matching_tables = [
        table_name
        for table_name, df in tables.items()
        if result_type in classify_table(table_name, df)
    ]
    return matching_tables or list(tables.keys())


def build_max_summary_table(
    df: pd.DataFrame,
    metric_columns: list[str],
    hover_columns: list[str],
) -> pd.DataFrame:
    """Find the max row for every metric in the selected summary table."""

    rows = []
    for metric_column in metric_columns:
        valid = df.dropna(subset=[metric_column])
        if valid.empty:
            continue

        max_index = valid[metric_column].idxmax()
        max_row = valid.loc[max_index]
        row = {
            "Metric": metric_column,
            "Max Value": max_row[metric_column],
        }
        for column in hover_columns:
            if column in max_row.index:
                row[column] = max_row[column]
        rows.append(row)

    return pd.DataFrame(rows).round(4)


def get_metric_max_index(df: pd.DataFrame, metric_column: str) -> object | None:
    """Return the row index of the maximum metric value."""

    valid = df.dropna(subset=[metric_column])
    if valid.empty:
        return None
    return valid[metric_column].idxmax()


def get_pair_feature_sets(dimension_columns: list[str]) -> dict[str, list[str]]:
    """Build 1D, 2D, and 3D feature sets from available dimensions."""

    feature_sets: dict[str, list[str]] = {}
    for column in dimension_columns:
        feature_sets[column] = [column]

    for pair in combinations(dimension_columns, 2):
        feature_sets["+".join(pair)] = list(pair)

    if len(dimension_columns) >= 3:
        feature_sets["+".join(dimension_columns[:3])] = dimension_columns[:3]

    return feature_sets


def fit_linear_regression(
    df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
) -> dict[str, object] | None:
    """Fit y = b0 + b1*x1 + ... and return coefficients and R2.

    여기서는 numpy.linalg.lstsq()로 가장 기본적인 선형회귀를 계산합니다.

    입력 예:
    - feature_columns=["L"], target_column="GM"
      -> GM = b0 + b1*L
    - feature_columns=["L", "B"], target_column="Max.BM"
      -> Max.BM = b0 + b1*L + b2*B

    반환값:
    - coefficients: 회귀계수
    - r2: 결정계수. 1에 가까울수록 설명력이 높습니다.
    - data: 결측치를 제거한 실제 학습 데이터
    - predicted: 회귀식으로 계산한 예측값
    """

    columns = [*feature_columns, target_column]
    clean = df[columns].dropna()
    if len(clean) < len(feature_columns) + 2:
        return None

    x = clean[feature_columns].to_numpy(dtype=float)
    y = clean[target_column].to_numpy(dtype=float)
    # design matrix의 첫 번째 열은 절편(intercept) b0를 계산하기 위한 1입니다.
    # 예: y = b0 + b1*x1 + b2*x2 형태로 만들기 위함입니다.
    design = np.column_stack([np.ones(len(clean)), x])

    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    predicted = design @ coefficients

    # R2 = 1 - (잔차 제곱합 / 전체 변동 제곱합)
    # 모델이 평균값만 쓰는 것보다 얼마나 더 잘 설명하는지 보는 지표입니다.
    residual_sum = float(np.sum((y - predicted) ** 2))
    total_sum = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - residual_sum / total_sum if total_sum > 0 else math.nan

    return {
        "rows": len(clean),
        "coefficients": coefficients,
        "r2": r2,
        "data": clean,
        "predicted": predicted,
    }


def build_r2_overview(
    df: pd.DataFrame,
    metric_columns: list[str],
    feature_sets: dict[str, list[str]],
) -> pd.DataFrame:
    """Compute R2 values for many metrics and feature sets.

    Trend Analysis 탭의 R2 overview 표를 만드는 함수입니다.
    metric 여러 개와 feature 조합 여러 개를 돌면서 R2를 계산합니다.
    예:
    - GM vs L
    - GM vs L+B
    - GM vs L+B+D
    - Max.BM vs L
    - Max.BM vs L+B
    """

    rows = []
    for metric_column in metric_columns:
        for model_name, feature_columns in feature_sets.items():
            fit = fit_linear_regression(df, feature_columns, metric_column)
            if fit is None:
                continue
            rows.append(
                {
                    "Metric": metric_column,
                    "Model": model_name,
                    "Features": ", ".join(feature_columns),
                    "Rows": fit["rows"],
                    "R2": fit["r2"],
                }
            )

    if not rows:
        return pd.DataFrame(columns=["Metric", "Model", "Features", "Rows", "R2"])

    return pd.DataFrame(rows).sort_values(
        ["Metric", "R2"],
        ascending=[True, False],
    )


def build_1d_trend_line(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
) -> pd.DataFrame:
    """Create a sorted trend line for a 1D linear model."""

    fit = fit_linear_regression(df, [x_column], y_column)
    if fit is None:
        return pd.DataFrame(columns=[x_column, "Trend"])

    clean = fit["data"]
    coefficients = fit["coefficients"]
    x_values = np.linspace(clean[x_column].min(), clean[x_column].max(), 50)
    y_values = coefficients[0] + coefficients[1] * x_values

    return pd.DataFrame({x_column: x_values, "Trend": y_values})


def compare_constraint(series: pd.Series, operator: str, value: float) -> pd.Series:
    """Return a boolean mask for one numeric constraint."""

    if operator == "<=":
        return series <= value
    if operator == ">=":
        return series >= value
    if operator == "<":
        return series < value
    if operator == ">":
        return series > value
    if operator == "==":
        return series == value
    raise ValueError(f"Unsupported constraint operator: {operator}")


def apply_constraints(
    df: pd.DataFrame,
    constraints: list[dict[str, object]],
) -> pd.DataFrame:
    """Remove rows that violate user-defined constraints.

    Constraint는 최적화 전에 "불가능한 case"를 제거하는 단계입니다.
    예를 들어 GM >= 4.0을 만족하지 못하면 설계 후보에서 제외합니다.
    """

    filtered = df.copy()
    for constraint in constraints:
        column = str(constraint["column"])
        operator = str(constraint["operator"])
        value = float(constraint["value"])

        if column not in filtered.columns:
            continue
        filtered = filtered[compare_constraint(filtered[column], operator, value)]

    return filtered


def find_hull_weight_column(columns: Iterable[str]) -> str | None:
    """Find the preferred Hull Steel Weight column when it exists."""

    return find_first_existing_column(columns, HULL_WEIGHT_COLUMN_CANDIDATES)


def normalize_objective_score(series: pd.Series, direction: str) -> pd.Series:
    """Normalize one objective so 1.0 is best and 0.0 is worst.

    Weighted ranking은 서로 단위가 다른 값을 더해야 합니다.
    예:
    - Hull Steel Weight: ton 단위
    - GM: m 단위
    - MPM: motion 단위

    단위가 다르면 그대로 더할 수 없으므로 0~1 점수로 바꿉니다.
    - direction="min": 작을수록 1점에 가깝게 변환
    - direction="max": 클수록 1점에 가깝게 변환
    """

    clean = series.astype(float)
    minimum = clean.min()
    maximum = clean.max()
    if pd.isna(minimum) or pd.isna(maximum) or maximum == minimum:
        return pd.Series(1.0, index=series.index)

    if direction == "min":
        return (maximum - clean) / (maximum - minimum)
    return (clean - minimum) / (maximum - minimum)


def build_weighted_score_table(
    df: pd.DataFrame,
    objective_specs: list[dict[str, object]],
) -> pd.DataFrame:
    """Build a weighted ranking table from user-selected objectives.

    objective_specs 예:
        [
            {"column": "Hull Steel Weight", "direction": "min", "weight": 3.0},
            {"column": "GM", "direction": "max", "weight": 1.0},
        ]

    계산 방식:
    1. 각 objective를 0~1 점수로 정규화합니다.
    2. 각 점수에 weight를 곱합니다.
    3. 전체 weight 합으로 나누어 Weighted Score를 만듭니다.
    4. Weighted Score가 큰 순서로 정렬합니다.
    """

    if not objective_specs:
        scored = df.copy()
        scored["Weighted Score"] = 0.0
        return scored

    scored = df.copy()
    weighted_sum = pd.Series(0.0, index=scored.index)
    total_weight = 0.0

    for spec in objective_specs:
        column = str(spec["column"])
        direction = str(spec["direction"])
        weight = float(spec["weight"])
        if column not in scored.columns or weight <= 0:
            continue

        score_column = f"Score: {column}"
        scored[score_column] = normalize_objective_score(
            scored[column],
            direction,
        ).fillna(0.0)
        weighted_sum = weighted_sum + scored[score_column] * weight
        total_weight += weight

    if total_weight == 0:
        scored["Weighted Score"] = 0.0
    else:
        scored["Weighted Score"] = weighted_sum / total_weight

    return scored.sort_values("Weighted Score", ascending=False).reset_index(drop=True)


def build_pareto_mask(
    df: pd.DataFrame,
    objective_columns: list[str],
    directions: list[str],
) -> pd.Series:
    """Return True for Pareto-efficient rows.

    Directions must be "min" or "max".  Internally all objectives are converted
    to minimization, then a row is dominated when another row is no worse in all
    objectives and strictly better in at least one objective.
    """

    # Pareto 계산은 objective 값이 비어 있으면 비교할 수 없습니다.
    # 그래서 objective_columns에 결측치가 있는 행은 Pareto 후보에서 제외합니다.
    clean = df[objective_columns].dropna()
    if clean.empty:
        return pd.Series(False, index=df.index)

    values = clean.to_numpy(dtype=float).copy()

    # Pareto 계산은 내부적으로 모두 "작을수록 좋다"는 minimization 문제로 바꿉니다.
    # max objective는 부호를 반대로 바꾸면 작을수록 좋은 값처럼 비교할 수 있습니다.
    for column_index, direction in enumerate(directions):
        if direction == "max":
            values[:, column_index] *= -1.0

    # is_efficient=True이면 아직 Pareto 후보로 남아 있다는 뜻입니다.
    is_efficient = np.ones(values.shape[0], dtype=bool)
    for row_index, row in enumerate(values):
        if not is_efficient[row_index]:
            continue

        # dominated=True인 행이 하나라도 있으면 현재 row는 다른 row에게 지배됩니다.
        # 지배 조건:
        # - 다른 row가 모든 objective에서 현재 row보다 같거나 좋고
        # - 적어도 하나의 objective에서는 더 좋다
        dominated = np.all(values <= row, axis=1) & np.any(values < row, axis=1)
        if np.any(dominated):
            is_efficient[row_index] = False

    mask = pd.Series(False, index=df.index)
    mask.loc[clean.index] = is_efficient
    return mask


def sort_optimal_cases(
    df: pd.DataFrame,
    objective_column: str,
    direction: str,
) -> pd.DataFrame:
    """Sort feasible/Pareto cases by the economic objective."""

    ascending = direction == "min"
    return df.sort_values(objective_column, ascending=ascending).reset_index(drop=True)
