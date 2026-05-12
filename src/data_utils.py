"""Small data preparation helpers.

이 파일은 pandas DataFrame을 대시보드에서 쓰기 좋은 형태로 다듬습니다.
각 함수는 가능한 한 한 가지 일만 하도록 작게 나누었습니다.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def strip_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """컬럼명 앞뒤 공백을 제거합니다."""

    cleaned = df.copy()
    cleaned.columns = [str(column).strip() for column in cleaned.columns]
    return cleaned


def drop_fully_empty_rows(df: pd.DataFrame) -> pd.DataFrame:
    """모든 값이 비어 있는 행을 제거합니다."""

    return df.dropna(how="all").reset_index(drop=True)


def coerce_series_to_number(series: pd.Series) -> pd.Series:
    """Series를 숫자로 변환합니다. 변환할 수 없는 값은 NaN이 됩니다."""

    return pd.to_numeric(series, errors="coerce")


def numeric_ratio(original: pd.Series, converted: pd.Series) -> float:
    """비어 있지 않은 원본 값 중 숫자로 변환된 값의 비율을 계산합니다."""

    non_empty_count = original.notna().sum()
    if non_empty_count == 0:
        return 0.0
    return converted.notna().sum() / non_empty_count


def should_use_numeric_conversion(
    original: pd.Series,
    converted: pd.Series,
    min_ratio: float = 0.8,
) -> bool:
    """문자 컬럼을 숫자 컬럼으로 바꿔도 되는지 판단합니다.

    SQLite에서 숫자가 TEXT로 저장되는 경우가 꽤 있습니다.
    예를 들어 "335", "65"처럼 들어온 컬럼은 숫자로 바꾸는 편이 차트에 좋습니다.
    반대로 FullLoad 같은 Loading Condition 컬럼은 숫자로 바꾸면 안 됩니다.
    """

    return numeric_ratio(original, converted) >= min_ratio


def coerce_possible_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """숫자처럼 보이는 컬럼을 실제 숫자 dtype으로 변환합니다."""

    converted_df = df.copy()
    for column in converted_df.columns:
        converted = coerce_series_to_number(converted_df[column])
        if should_use_numeric_conversion(converted_df[column], converted):
            converted_df[column] = converted
    return converted_df


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """DB에서 읽은 원본 DataFrame을 대시보드용으로 정리합니다."""

    cleaned = strip_column_names(df)
    cleaned = drop_fully_empty_rows(cleaned)
    cleaned = coerce_possible_numeric_columns(cleaned)
    return cleaned


def find_first_existing_column(
    columns: Iterable[str],
    candidates: Iterable[str],
) -> str | None:
    """후보 컬럼명 중 실제로 존재하는 첫 번째 컬럼을 찾습니다."""

    column_set = set(columns)
    for candidate in candidates:
        if candidate in column_set:
            return candidate
    return None


def get_existing_columns(
    columns: Iterable[str],
    wanted_columns: Iterable[str],
) -> list[str]:
    """원하는 컬럼 목록 중 실제 DataFrame에 있는 컬럼만 반환합니다."""

    column_set = set(columns)
    return [column for column in wanted_columns if column in column_set]


def get_numeric_columns(df: pd.DataFrame, exclude_columns: Iterable[str] = ()) -> list[str]:
    """차트의 Y축으로 쓸 수 있는 숫자 컬럼 목록을 반환합니다."""

    exclude_set = set(exclude_columns)
    numeric_columns = df.select_dtypes(include="number").columns
    return [column for column in numeric_columns if column not in exclude_set]


def get_text_columns(df: pd.DataFrame) -> list[str]:
    """문자/범주형 필터로 쓰기 좋은 컬럼 목록을 반환합니다."""

    non_numeric_columns = df.select_dtypes(exclude="number").columns
    return list(non_numeric_columns)


def sorted_unique_values(series: pd.Series) -> list:
    """필터 UI에 보여줄 고유값 목록을 정렬해서 반환합니다."""

    values = series.dropna().unique().tolist()
    return sorted(values, key=lambda value: str(value))


def apply_value_filter(
    df: pd.DataFrame,
    column: str | None,
    selected_values: list,
) -> pd.DataFrame:
    """선택한 값만 남기는 필터입니다."""

    if column is None or not selected_values:
        return df
    return df[df[column].isin(selected_values)]


def apply_numeric_range_filter(
    df: pd.DataFrame,
    column: str,
    selected_range: tuple[float, float],
) -> pd.DataFrame:
    """숫자 컬럼을 최소~최대 범위로 필터링합니다."""

    minimum, maximum = selected_range
    return df[df[column].between(minimum, maximum, inclusive="both")]


def sort_dataframe(df: pd.DataFrame, sort_columns: list[str]) -> pd.DataFrame:
    """존재하는 컬럼 기준으로 DataFrame을 정렬합니다."""

    existing_sort_columns = [column for column in sort_columns if column in df.columns]
    if not existing_sort_columns:
        return df
    return df.sort_values(existing_sort_columns).reset_index(drop=True)


def build_group_summary(
    df: pd.DataFrame,
    group_columns: list[str],
    metric_column: str,
) -> pd.DataFrame:
    """선택한 metric을 그룹별 count/mean/min/max로 요약합니다."""

    summary = (
        df.groupby(group_columns, dropna=False)[metric_column]
        .agg(["count", "mean", "min", "max"])
        .reset_index()
    )
    return summary.round(3)


def select_existing_display_columns(
    df: pd.DataFrame,
    preferred_columns: list[str],
) -> list[str]:
    """상세 테이블에 보여줄 컬럼을 고릅니다."""

    existing_preferred = [column for column in preferred_columns if column in df.columns]
    remaining = [column for column in df.columns if column not in existing_preferred]
    return existing_preferred + remaining
