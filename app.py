"""FPSO Stability/Motion result dashboard.

실행:
    streamlit run app.py

이 앱은 SQLite DB에 저장된 FPSO 계산 결과를 읽고,
L/B/D 제원별로 Stability 및 Motion 결과 컬럼을 비교해서 보여줍니다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.charts import make_metric_box_chart, make_metric_trend_chart
from src.config import (
    CONDITION_COLUMN_CANDIDATES,
    DEFAULT_DB_PATH,
    DEFAULT_DIMENSION_COLUMNS,
    UPLOAD_DIR,
)
from src.data_utils import (
    apply_numeric_range_filter,
    apply_value_filter,
    build_group_summary,
    find_first_existing_column,
    get_existing_columns,
    get_numeric_columns,
    prepare_dataframe,
    select_existing_display_columns,
    sort_dataframe,
    sorted_unique_values,
)
from src.db import list_tables, load_table


def configure_page() -> None:
    """Streamlit 페이지의 기본 설정을 잡습니다."""

    st.set_page_config(
        page_title="FPSO Stability & Motion Dashboard",
        layout="wide",
    )


def render_title() -> None:
    """앱 상단 제목을 출력합니다."""

    st.title("FPSO Stability & Motion Dashboard")
    st.caption("SQLite DB에 저장된 계산 결과를 L, B, D 제원별로 비교합니다.")


def save_uploaded_file(uploaded_file) -> Path:
    """Streamlit 업로드 파일을 로컬 임시 폴더에 저장하고 경로를 반환합니다."""

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_file_name = Path(uploaded_file.name).name
    target_path = UPLOAD_DIR / safe_file_name
    target_path.write_bytes(uploaded_file.getbuffer())
    return target_path


def clean_path_text(path_text: str) -> str:
    """사용자가 붙여 넣은 경로 문자열을 Path에 넣기 좋은 형태로 다듬습니다."""

    return path_text.strip().strip('"').strip("'")


def get_database_path_from_sidebar() -> Path:
    """사이드바에서 사용할 SQLite DB 경로를 결정합니다."""

    st.sidebar.header("Database")

    uploaded_file = st.sidebar.file_uploader(
        "SQLite DB 업로드",
        type=["db", "sqlite", "sqlite3"],
    )
    if uploaded_file is not None:
        return save_uploaded_file(uploaded_file)

    default_text = str(DEFAULT_DB_PATH) if DEFAULT_DB_PATH.exists() else ""
    typed_path = st.sidebar.text_input("또는 로컬 DB 경로", value=default_text)
    cleaned_path = clean_path_text(typed_path)
    return Path(cleaned_path) if cleaned_path else DEFAULT_DB_PATH


@st.cache_data(show_spinner=False)
def get_cached_table_names(db_path_text: str, db_mtime_ns: int) -> list[str]:
    """테이블 목록을 캐시해서 같은 DB를 반복 조회하지 않게 합니다."""

    # db_mtime_ns는 함수 안에서 직접 쓰지 않지만, DB 파일이 바뀌었을 때
    # Streamlit 캐시를 새로 계산하게 만드는 캐시 키 역할을 합니다.
    _ = db_mtime_ns
    return list_tables(Path(db_path_text))


@st.cache_data(show_spinner=False)
def get_cached_table_data(
    db_path_text: str,
    db_mtime_ns: int,
    table_name: str,
) -> pd.DataFrame:
    """선택한 테이블 데이터를 캐시해서 화면 반응을 빠르게 합니다."""

    _ = db_mtime_ns
    raw_df = load_table(Path(db_path_text), table_name)
    return prepare_dataframe(raw_df)


def get_file_mtime_ns(file_path: Path) -> int:
    """파일 수정 시간을 나노초 단위 정수로 반환합니다."""

    return file_path.stat().st_mtime_ns


def select_table(db_path: Path, db_mtime_ns: int) -> str:
    """DB 안의 테이블 중 하나를 선택합니다."""

    table_names = get_cached_table_names(str(db_path), db_mtime_ns)
    if not table_names:
        st.error("선택한 DB 안에서 사용자 테이블을 찾지 못했습니다.")
        st.stop()

    if len(table_names) == 1:
        st.sidebar.info(f"테이블: {table_names[0]}")
        return table_names[0]

    return st.sidebar.selectbox("테이블 선택", table_names)


def get_condition_column(df: pd.DataFrame) -> str | None:
    """Loading Condition으로 사용할 컬럼을 찾습니다."""

    return find_first_existing_column(df.columns, CONDITION_COLUMN_CANDIDATES)


def render_condition_filter(
    df: pd.DataFrame,
    condition_column: str | None,
) -> list:
    """Loading Condition 필터 UI를 만들고 선택값을 반환합니다."""

    if condition_column is None:
        return []

    options = sorted_unique_values(df[condition_column])
    return st.sidebar.multiselect(
        f"{condition_column} 필터",
        options=options,
        default=options,
    )


def render_dimension_range_filters(
    df: pd.DataFrame,
    dimension_columns: list[str],
) -> dict[str, tuple[float, float]]:
    """L/B/D 같은 숫자 제원 컬럼의 범위 필터 UI를 만듭니다."""

    selected_ranges: dict[str, tuple[float, float]] = {}
    for column in dimension_columns:
        if not pd.api.types.is_numeric_dtype(df[column]):
            continue

        minimum = float(df[column].min())
        maximum = float(df[column].max())
        if minimum == maximum:
            continue

        selected_ranges[column] = st.sidebar.slider(
            f"{column} 범위",
            min_value=minimum,
            max_value=maximum,
            value=(minimum, maximum),
        )
    return selected_ranges


def apply_sidebar_filters(
    df: pd.DataFrame,
    condition_column: str | None,
    selected_conditions: list,
    selected_ranges: dict[str, tuple[float, float]],
) -> pd.DataFrame:
    """사이드바에서 선택한 조건들을 DataFrame에 적용합니다."""

    filtered = apply_value_filter(df, condition_column, selected_conditions)
    for column, selected_range in selected_ranges.items():
        filtered = apply_numeric_range_filter(filtered, column, selected_range)
    return filtered


def select_metric_column(
    df: pd.DataFrame,
    dimension_columns: list[str],
) -> str:
    """Y축으로 볼 결과 컬럼을 선택합니다."""

    metric_columns = get_numeric_columns(df, exclude_columns=dimension_columns)
    if not metric_columns:
        st.error("차트로 표시할 숫자 결과 컬럼을 찾지 못했습니다.")
        st.stop()

    return st.sidebar.selectbox("결과 컬럼 선택", metric_columns)


def get_hover_columns(
    df: pd.DataFrame,
    dimension_columns: list[str],
    condition_column: str | None,
    metric_column: str,
) -> list[str]:
    """Plotly hover에 표시할 컬럼 목록을 정리합니다."""

    preferred = dimension_columns + [condition_column, metric_column]
    return [column for column in preferred if column in df.columns]


def get_group_columns(
    dimension_column: str,
    condition_column: str | None,
) -> list[str]:
    """요약표에서 사용할 그룹 컬럼을 정합니다."""

    if condition_column is None:
        return [dimension_column]
    return [dimension_column, condition_column]


def render_dimension_view(
    df: pd.DataFrame,
    dimension_column: str,
    metric_column: str,
    condition_column: str | None,
    all_dimension_columns: list[str],
) -> None:
    """L별/B별/D별 탭 안의 차트와 표를 그립니다."""

    st.subheader(f"{dimension_column}별 {metric_column}")
    st.caption("위 그래프는 평균 추세, 아래 그래프는 원자료 분포를 보여줍니다.")

    hover_columns = get_hover_columns(
        df,
        all_dimension_columns,
        condition_column,
        metric_column,
    )

    trend_chart = make_metric_trend_chart(
        df=df,
        x_column=dimension_column,
        y_column=metric_column,
        color_column=condition_column,
        hover_columns=hover_columns,
    )
    st.plotly_chart(trend_chart, use_container_width=True)

    box_chart = make_metric_box_chart(
        df=df,
        x_column=dimension_column,
        y_column=metric_column,
        color_column=condition_column,
    )
    st.plotly_chart(box_chart, use_container_width=True)

    group_columns = get_group_columns(dimension_column, condition_column)
    summary = build_group_summary(df, group_columns, metric_column)
    st.dataframe(summary, use_container_width=True, hide_index=True)


def render_dimension_tabs(
    df: pd.DataFrame,
    dimension_columns: list[str],
    metric_column: str,
    condition_column: str | None,
) -> None:
    """L/B/D 탭을 만들고 각 탭의 내용을 그립니다."""

    tabs = st.tabs([f"{column}별" for column in dimension_columns])
    for tab, dimension_column in zip(tabs, dimension_columns):
        with tab:
            render_dimension_view(
                df=df,
                dimension_column=dimension_column,
                metric_column=metric_column,
                condition_column=condition_column,
                all_dimension_columns=dimension_columns,
            )


def render_detail_table(
    df: pd.DataFrame,
    dimension_columns: list[str],
    condition_column: str | None,
    metric_column: str,
) -> None:
    """필터 적용 후 원본 행을 확인할 수 있는 상세 테이블을 보여줍니다."""

    display_columns = select_existing_display_columns(
        df,
        dimension_columns + [condition_column, metric_column],
    )
    sorted_df = sort_dataframe(df[display_columns], dimension_columns)

    with st.expander("필터 적용 데이터 보기", expanded=False):
        st.dataframe(sorted_df, use_container_width=True, hide_index=True)


def stop_if_database_missing(db_path: Path) -> None:
    """DB 파일이 없을 때 사용자가 바로 이해할 수 있는 안내를 보여줍니다."""

    if db_path.exists():
        return

    st.warning("SQLite DB 파일을 찾지 못했습니다.")
    st.code("python scripts/create_sample_db.py", language="powershell")
    st.write("위 명령으로 샘플 DB를 만들거나, 사이드바에서 실제 DB 파일을 업로드해 주세요.")
    st.stop()


def main() -> None:
    """Streamlit 앱의 실행 흐름입니다."""

    configure_page()
    render_title()

    db_path = get_database_path_from_sidebar()
    stop_if_database_missing(db_path)
    db_mtime_ns = get_file_mtime_ns(db_path)

    table_name = select_table(db_path, db_mtime_ns)
    df = get_cached_table_data(str(db_path), db_mtime_ns, table_name)

    dimension_columns = get_existing_columns(df.columns, DEFAULT_DIMENSION_COLUMNS)
    if not dimension_columns:
        st.error("L, B, D 중 하나 이상의 제원 컬럼이 필요합니다.")
        st.stop()

    condition_column = get_condition_column(df)
    selected_conditions = render_condition_filter(df, condition_column)
    selected_ranges = render_dimension_range_filters(df, dimension_columns)
    filtered_df = apply_sidebar_filters(
        df=df,
        condition_column=condition_column,
        selected_conditions=selected_conditions,
        selected_ranges=selected_ranges,
    )

    if filtered_df.empty:
        st.warning("필터 조건에 맞는 데이터가 없습니다.")
        st.stop()

    metric_column = select_metric_column(filtered_df, dimension_columns)

    st.metric("행 개수", len(filtered_df))
    render_dimension_tabs(
        df=filtered_df,
        dimension_columns=dimension_columns,
        metric_column=metric_column,
        condition_column=condition_column,
    )
    render_detail_table(
        df=filtered_df,
        dimension_columns=dimension_columns,
        condition_column=condition_column,
        metric_column=metric_column,
    )


if __name__ == "__main__":
    main()
