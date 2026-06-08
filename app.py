"""FPSO Stability/Motion result dashboard.

이 파일은 Streamlit 화면을 실제로 구성하는 "메인 파일"입니다.
초보자라면 아래 순서로 읽으면 전체 흐름을 이해하기 쉽습니다.

1. main()
   - 앱이 시작되면 가장 먼저 실행되는 함수입니다.
   - DB를 고르고, 데이터를 읽고, 5개 탭을 만듭니다.

2. get_database_path_from_sidebar()
   - 사용자가 사이드바에서 DB 파일을 업로드하거나 경로를 입력하는 부분입니다.
   - C# 코드에서 --db 또는 환경변수로 넘긴 DB 경로도 여기서 기본값으로 쓰입니다.

3. get_cached_database_tables()
   - SQLite DB 안의 모든 테이블을 pandas DataFrame으로 읽습니다.
   - Streamlit 캐시를 써서 같은 DB를 반복해서 느리게 읽지 않도록 합니다.

4. render_summary_tab(), render_individual_plot_tab(), render_trend_tab(),
   render_statistics_tab(), render_optimization_tab()
   - 화면에 보이는 5개 탭을 각각 담당합니다.

중요한 설계 방향:
- 이 파일은 "화면 배치"를 담당합니다.
- 실제 분석 계산은 src/fpso_analysis.py에 최대한 분리했습니다.
- 실제 Plotly 그래프 생성은 src/charts.py에 분리했습니다.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

# 그래프를 만드는 함수들입니다.
# app.py 안에서 직접 Plotly 옵션을 길게 쓰지 않기 위해 src/charts.py로 분리했습니다.
from src.charts import (
    make_2d_metric_scatter,
    make_3d_metric_scatter,
    make_case_bar_chart,
    make_case_line_chart,
    make_correlation_heatmap,
    make_pareto_scatter,
    make_summary_max_scatter,
    make_trend_with_line_chart,
)

# 프로젝트 기본 설정값입니다.
# DEFAULT_DB_PATH는 샘플 DB 경로이고, UPLOAD_DIR은 업로드한 DB를 잠시 저장할 폴더입니다.
from src.config import DEFAULT_DB_PATH, UPLOAD_DIR

# pandas DataFrame을 정리하거나 필터링하는 아주 작은 유틸리티 함수들입니다.
from src.data_utils import (
    apply_numeric_range_filter,
    apply_value_filter,
    prepare_dataframe,
    select_existing_display_columns,
    sort_dataframe,
    sorted_unique_values,
)

# SQLite DB에서 테이블 목록과 테이블 데이터를 읽는 함수입니다.
from src.db import list_tables, load_table

# FPSO 결과 데이터의 컬럼 추정, 회귀분석, Pareto set, weighted score 계산 등
# 화면과 독립적인 분석 로직은 이 모듈에 모아 두었습니다.
from src.fpso_analysis import (
    RESULT_TYPES,
    add_case_label,
    apply_constraints,
    build_1d_trend_line,
    build_case_coverage_table,
    build_data_quality_report,
    build_max_summary_table,
    build_pareto_mask,
    build_r2_overview,
    build_table_profiles,
    build_weighted_score_table,
    choose_default_summary_table,
    filter_by_case_labels,
    find_axis_column,
    find_default_result_column,
    find_heading_column,
    find_hull_weight_column,
    fit_linear_regression,
    get_case_columns,
    get_case_hover_columns,
    get_dimension_columns,
    get_metric_max_index,
    get_numeric_result_columns,
    get_pair_feature_sets,
    get_result_type_table_options,
    get_tables_with_dimensions,
    get_unique_cases,
    sort_optimal_cases,
)


# -----------------------------------------------------------------------------
# 1. 앱 기본 설정 및 DB 경로 입력
# -----------------------------------------------------------------------------
# 이 구역의 함수들은 화면 맨 처음에 필요한 준비 작업을 담당합니다.
# Streamlit 페이지 제목을 설정하고, 사용자가 어떤 DB를 볼지 결정합니다.


def configure_page() -> None:
    """Configure the Streamlit page."""

    st.set_page_config(
        page_title="FPSO Stability & Motion Dashboard",
        layout="wide",
    )


def render_title() -> None:
    """Render the page title."""

    st.title("FPSO Stability & Motion Dashboard")
    st.caption(
        "Compare FPSO stability, motion, trends, statistics, and optimal dimensions."
    )


def save_uploaded_file(uploaded_file) -> Path:
    """Save an uploaded DB file to a local temporary folder."""

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_file_name = Path(uploaded_file.name).name
    target_path = UPLOAD_DIR / safe_file_name
    target_path.write_bytes(uploaded_file.getbuffer())
    return target_path


def clean_path_text(path_text: str) -> str:
    """Clean a pasted path string before turning it into a Path."""

    return path_text.strip().strip('"').strip("'")


def parse_startup_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Read user arguments passed after Streamlit's own arguments.

    Example:
        streamlit run app.py -- --db "C:\\results\\case_001.db"
    """

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--db", dest="db_path", default="")
    args, _ = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    return args


def get_cli_database_path() -> str:
    """Read the DB path passed from C# or a terminal through --db."""

    return clean_path_text(parse_startup_args().db_path)


def get_env_database_path() -> str:
    """Read the DB path passed through the FPSO_DASHBOARD_DB environment variable."""

    return clean_path_text(os.environ.get("FPSO_DASHBOARD_DB", ""))


def get_query_database_path() -> str:
    """Read the DB path passed through the URL query string."""

    query_value = st.query_params.get("db", "")
    if isinstance(query_value, list):
        query_value = query_value[0] if query_value else ""
    return clean_path_text(str(query_value))


def get_default_database_path_text() -> str:
    """Choose the default DB path shown in the sidebar."""

    for path_text in (
        get_query_database_path(),
        get_cli_database_path(),
        get_env_database_path(),
    ):
        if path_text:
            return path_text

    return str(DEFAULT_DB_PATH) if DEFAULT_DB_PATH.exists() else ""


def get_database_path_from_sidebar() -> Path:
    """Choose the SQLite DB path from upload, typed path, or default sample DB.

    DB를 선택하는 우선순위는 다음과 같습니다.
    1. 사용자가 Streamlit 사이드바에서 직접 업로드한 DB
    2. 사용자가 사이드바 text_input에 직접 입력한 로컬 DB 경로
    3. C# 실행 코드나 URL query로 넘어온 DB 경로
    4. 샘플 DB 경로

    C#에서 dashboard를 자동 실행할 때는 보통 3번 방식으로 DB 경로가 들어옵니다.
    """

    st.sidebar.header("Database")

    uploaded_file = st.sidebar.file_uploader(
        "Upload SQLite DB",
        type=["db", "sqlite", "sqlite3"],
    )
    if uploaded_file is not None:
        # Streamlit 업로드 객체는 메모리에 올라온 파일입니다.
        # pandas/sqlite가 경로 기반으로 읽을 수 있도록 임시 폴더에 저장합니다.
        return save_uploaded_file(uploaded_file)

    default_text = get_default_database_path_text()
    typed_path = st.sidebar.text_input("Or enter local DB path", value=default_text)
    cleaned_path = clean_path_text(typed_path)
    return Path(cleaned_path) if cleaned_path else DEFAULT_DB_PATH


@st.cache_data(show_spinner=False)
def get_cached_table_names(db_path_text: str, db_mtime_ns: int) -> list[str]:
    """Load table names and refresh the cache when the DB file changes.

    Streamlit의 @st.cache_data는 같은 입력값이면 함수 결과를 재사용합니다.
    그래서 DB 파일을 매번 다시 읽지 않아 화면 반응이 빨라집니다.

    db_mtime_ns는 함수 안에서 직접 쓰지는 않지만 매우 중요합니다.
    DB 파일 수정 시간이 바뀌면 입력값도 바뀌므로 캐시가 자동으로 갱신됩니다.
    """

    _ = db_mtime_ns
    return list_tables(Path(db_path_text))


@st.cache_data(show_spinner=False)
def get_cached_database_tables(
    db_path_text: str,
    db_mtime_ns: int,
) -> dict[str, pd.DataFrame]:
    """Load every user table in the SQLite DB as prepared DataFrames.

    반환 형태는 {"테이블명": DataFrame} 입니다.
    예:
        {
            "SF": sf_dataframe,
            "BM": bm_dataframe,
            "ShortTermMPM": mpm_dataframe,
        }

    prepare_dataframe()에서는 컬럼명 공백 제거, 빈 행 제거, 숫자형 변환을 처리합니다.
    """

    _ = db_mtime_ns
    db_path = Path(db_path_text)
    return {
        table_name: prepare_dataframe(load_table(db_path, table_name))
        for table_name in list_tables(db_path)
    }


def get_file_mtime_ns(file_path: Path) -> int:
    """Return the DB modification time as a cache key."""

    return file_path.stat().st_mtime_ns


def stop_if_database_missing(db_path: Path) -> None:
    """Stop early when no DB file is available."""

    if db_path.exists():
        return

    st.warning("SQLite DB file was not found.")
    st.code("python scripts/create_sample_db.py", language="powershell")
    st.write(
        "Create a sample DB with the command above, or upload a real DB file from the sidebar."
    )
    st.stop()


def get_option_index(options: list[str], selected_option: str | None) -> int:
    """Return a safe selectbox index for a preferred option."""

    if selected_option in options:
        return options.index(selected_option)
    return 0


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Convert a DataFrame to UTF-8 CSV bytes that open cleanly in Excel."""

    return df.to_csv(index=False).encode("utf-8-sig")


def render_csv_download(
    df: pd.DataFrame,
    label: str,
    file_name: str,
    key: str,
) -> None:
    """Render a CSV download button when the DataFrame has data.

    Streamlit의 download_button은 bytes 데이터를 받아 파일로 내려줍니다.
    CSV를 UTF-8 with BOM으로 만들면 Excel에서 한글 컬럼명도 비교적 안전하게 열립니다.
    """

    if df.empty:
        return

    st.download_button(
        label=label,
        data=dataframe_to_csv_bytes(df),
        file_name=file_name,
        mime="text/csv",
        key=key,
    )


def render_table_overview(tables: dict[str, pd.DataFrame]) -> None:
    """Show compact DB table metadata in the sidebar.

    실제 C# 결과 DB를 붙이면 테이블이 여러 개 있을 수 있습니다.
    이 expander는 어떤 테이블이 로딩되었고, 어떤 결과 타입으로 인식되었는지
    빠르게 확인하기 위한 작은 점검판입니다.
    """

    profiles = build_table_profiles(tables)
    with st.sidebar.expander("Loaded tables", expanded=False):
        st.dataframe(profiles, use_container_width=True, hide_index=True)


def render_data_quality_expander(
    tables: dict[str, pd.DataFrame],
    summary_df: pd.DataFrame,
) -> None:
    """Render data health checks that help validate a new result DB."""

    quality_report = build_data_quality_report(tables)
    coverage_table = build_case_coverage_table(summary_df)

    with st.expander("Data quality diagnostics", expanded=False):
        st.dataframe(quality_report, use_container_width=True, hide_index=True)
        render_csv_download(
            quality_report,
            "Download quality report",
            "fpso_data_quality_report.csv",
            "download_quality_report",
        )

        if not coverage_table.empty:
            st.subheader("Case coverage")
            st.dataframe(coverage_table, use_container_width=True, hide_index=True)
            render_csv_download(
                coverage_table,
                "Download case coverage",
                "fpso_case_coverage.csv",
                "download_case_coverage",
            )


def select_summary_table(tables: dict[str, pd.DataFrame]) -> str:
    """Select the table used as the main case summary."""

    candidate_tables = get_tables_with_dimensions(tables) or list(tables.keys())
    default_table = choose_default_summary_table(
        {table_name: tables[table_name] for table_name in candidate_tables}
    )

    return st.sidebar.selectbox(
        "Summary source table",
        candidate_tables,
        index=get_option_index(candidate_tables, default_table),
    )


def render_condition_filter(df: pd.DataFrame, condition_column: str | None) -> list:
    """Render a loading-condition filter."""

    if condition_column is None:
        return []

    options = sorted_unique_values(df[condition_column])
    return st.sidebar.multiselect(
        f"{condition_column} filter",
        options=options,
        default=options,
    )


def render_dimension_range_filters(
    df: pd.DataFrame,
    dimension_columns: list[str],
) -> dict[str, tuple[float, float]]:
    """Render L/B/D range sliders."""

    selected_ranges: dict[str, tuple[float, float]] = {}
    for column in dimension_columns:
        if not pd.api.types.is_numeric_dtype(df[column]):
            continue

        minimum = float(df[column].min())
        maximum = float(df[column].max())
        if minimum == maximum:
            continue

        selected_ranges[column] = st.sidebar.slider(
            f"{column} range",
            min_value=minimum,
            max_value=maximum,
            value=(minimum, maximum),
        )
    return selected_ranges


def build_filter_state(summary_df: pd.DataFrame) -> dict[str, object]:
    """Build global filter state from the selected summary table.

    이 앱은 여러 테이블(SF, BM, GZ, RAO, ShortTerm MPM)을 동시에 다룰 수 있습니다.
    그런데 L/B/D 범위와 Loading Condition 필터는 모든 탭에 공통으로 적용되는 편이
    사용하기 쉽습니다.

    그래서 사이드바에서 선택한 필터 정보를 dict 하나로 묶어 두고,
    각 탭에서 apply_filter_state()로 재사용합니다.
    """

    dimension_columns = get_dimension_columns(summary_df)
    # get_case_hover_columns()는 L, B, D, LC처럼 case를 설명하는 컬럼을 반환합니다.
    # 그중 마지막이 보통 LC이므로 Loading Condition 후보로 씁니다.
    condition_columns = get_case_hover_columns(summary_df)
    condition_column = condition_columns[-1] if condition_columns else None
    if condition_column in dimension_columns:
        condition_column = None

    st.sidebar.header("Global filters")
    selected_conditions = render_condition_filter(summary_df, condition_column)
    selected_ranges = render_dimension_range_filters(summary_df, dimension_columns)

    return {
        "dimension_ranges": selected_ranges,
        "condition_column": condition_column,
        "selected_conditions": selected_conditions,
    }


def apply_filter_state(
    df: pd.DataFrame,
    filter_state: dict[str, object],
) -> pd.DataFrame:
    """Apply global filters to any table that contains the relevant columns.

    어떤 테이블은 L/B/D/LC를 모두 갖고 있고, 어떤 테이블은 일부만 가질 수 있습니다.
    예를 들어 RAO 테이블에는 Heading, Frequency까지 추가될 수 있습니다.
    그래서 필터 컬럼이 해당 테이블에 있을 때만 적용합니다.
    """

    filtered = df.copy()
    condition_column = filter_state["condition_column"]
    selected_conditions = filter_state["selected_conditions"]
    if condition_column in filtered.columns:
        filtered = apply_value_filter(filtered, condition_column, selected_conditions)

    selected_ranges = filter_state["dimension_ranges"]
    for column, selected_range in selected_ranges.items():
        if column in filtered.columns and pd.api.types.is_numeric_dtype(filtered[column]):
            filtered = apply_numeric_range_filter(filtered, column, selected_range)

    return filtered


def get_summary_metric_columns(df: pd.DataFrame) -> list[str]:
    """Return numeric output columns for summary/stat/trend/optimization tabs."""

    case_columns = get_case_columns(df)
    return get_numeric_result_columns(
        df,
        exclude_columns=case_columns,
        exclude_axis_columns=True,
    )


def render_summary_tab(
    tables: dict[str, pd.DataFrame],
    summary_df: pd.DataFrame,
    filter_state: dict[str, object],
) -> None:
    """Render max-result summary with a red point for the selected metric max.

    Summary 탭의 목적:
    - 전체 case 중 각 결과 컬럼의 최대값을 찾습니다.
    - 사용자가 선택한 metric에 대해 최대값 case를 빨간 점으로 강조합니다.
    - hover에 L, B, D, LC를 표시해서 어떤 제원/조건인지 바로 알 수 있게 합니다.
    """

    # 먼저 사이드바의 공통 필터를 적용합니다.
    # 이 filtered_df가 Summary 탭에서 실제로 보여줄 데이터입니다.
    filtered_df = apply_filter_state(summary_df, filter_state)

    # Summary/Trend/Statistics/Optimization에서 사용할 "결과 컬럼" 후보를 찾습니다.
    # L/B/D/LC/T 같은 case 설명 컬럼은 제외하고, GM/Max.SF/Max.BM 같은 숫자 결과만 남깁니다.
    metric_columns = get_summary_metric_columns(filtered_df)
    hover_columns = get_case_hover_columns(filtered_df)
    dimension_columns = get_dimension_columns(filtered_df)
    condition_column = filter_state["condition_column"]

    if filtered_df.empty:
        st.warning("No summary rows match the current filters.")
        return
    if not metric_columns:
        st.warning("No numeric output columns were found in the summary source table.")
        return

    render_data_quality_expander(tables, filtered_df)

    count_col, metric_col = st.columns(2)
    count_col.metric("Filtered cases", len(filtered_df))
    metric_col.metric("Output columns", len(metric_columns))

    # metric별 최대값 행을 표로 만듭니다.
    # 예: GM의 최대 case, Max.SF의 최대 case, Roll Tn의 최대 case 등.
    max_summary = build_max_summary_table(filtered_df, metric_columns, hover_columns)
    st.dataframe(max_summary, use_container_width=True, hide_index=True)
    render_csv_download(
        max_summary,
        "Download max summary",
        "fpso_max_summary.csv",
        "download_max_summary",
    )

    chart_col, dim_col = st.columns(2)
    chart_metric = chart_col.selectbox("Max-highlight metric", metric_columns)
    x_dimension = dim_col.selectbox(
        "Dimension axis",
        dimension_columns or filtered_df.select_dtypes(include="number").columns.tolist(),
    )

    # Plotly scatter에서 빨간 점으로 표시할 행 index입니다.
    max_index = get_metric_max_index(filtered_df, chart_metric)
    figure = make_summary_max_scatter(
        df=filtered_df,
        x_column=x_dimension,
        y_column=chart_metric,
        max_index=max_index,
        color_column=condition_column if condition_column in filtered_df.columns else None,
        hover_columns=[*hover_columns, chart_metric],
    )
    st.plotly_chart(figure, use_container_width=True)

    display_columns = select_existing_display_columns(
        filtered_df,
        [*hover_columns, chart_metric],
    )
    with st.expander("Summary source rows", expanded=False):
        source_rows = sort_dataframe(filtered_df[display_columns], dimension_columns)
        st.dataframe(
            source_rows,
            use_container_width=True,
            hide_index=True,
        )
        render_csv_download(
            source_rows,
            "Download filtered summary rows",
            "fpso_filtered_summary_rows.csv",
            "download_filtered_summary_rows",
        )


def get_selected_cases_from_table(
    case_df: pd.DataFrame,
    key: str,
) -> list[str]:
    """Allow users to click rows in a case table and return selected case labels.

    Streamlit 최신 버전에서는 st.dataframe(..., on_select="rerun")으로
    사용자가 클릭한 행 번호를 받을 수 있습니다.

    만약 Streamlit 버전이 낮아 on_select를 지원하지 않으면 TypeError가 나므로,
    그때는 단순 dataframe으로 보여주고 multiselect만 사용하게 둡니다.
    """

    display_df = case_df[["Case"]].copy()
    try:
        event = st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="multi-row",
            key=key,
        )
        selected_rows = event.selection.rows
    except TypeError:
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        selected_rows = []

    return [
        display_df.iloc[row_index]["Case"]
        for row_index in selected_rows
        if row_index < len(display_df)
    ]


def choose_cases_for_comparison(
    df: pd.DataFrame,
    case_columns: list[str],
    key_prefix: str,
) -> list[str]:
    """Choose one or two cases by clicking rows or using a multiselect.

    개별 결과 Plot 탭에서는 사용자가 "직접 두 case를 비교"하는 것이 중요합니다.
    그래서 두 가지 선택 방식을 제공합니다.
    - 테이블 행 클릭
    - multiselect에서 case label 직접 선택

    아무 것도 선택하지 않으면 처음 두 case를 기본 비교 대상으로 잡습니다.
    """

    case_df = get_unique_cases(df, case_columns)
    if case_df.empty:
        return []

    clicked_cases = get_selected_cases_from_table(case_df, f"{key_prefix}_case_table")
    manual_cases = st.multiselect(
        "Manual case selection",
        options=case_df["Case"].tolist(),
        default=[],
        key=f"{key_prefix}_manual_cases",
    )

    selected_cases = clicked_cases or manual_cases or case_df["Case"].head(2).tolist()
    if len(selected_cases) > 2:
        st.info("Using the first two selected cases for direct comparison.")
    return selected_cases[:2]


def build_plot_group_column(
    df: pd.DataFrame,
    heading_column: str | None,
) -> pd.DataFrame:
    """Create a display group column for selected case lines."""

    plot_df = df.copy()
    if heading_column and heading_column in plot_df.columns:
        plot_df["Plot Group"] = (
            plot_df["Case"].astype(str)
            + " | Heading="
            + plot_df[heading_column].astype(str)
        )
    else:
        plot_df["Plot Group"] = plot_df["Case"]
    return plot_df


def add_fallback_axis(df: pd.DataFrame) -> pd.DataFrame:
    """Add a point index when no physical x-axis column is found."""

    plot_df = df.copy()
    group_column = "Case" if "Case" in plot_df.columns else None
    if group_column:
        plot_df["Point"] = plot_df.groupby(group_column).cumcount() + 1
    else:
        plot_df["Point"] = range(1, len(plot_df) + 1)
    return plot_df


def render_heading_filter(df: pd.DataFrame, heading_column: str | None) -> pd.DataFrame:
    """Render an RAO heading filter when a heading column exists."""

    if heading_column is None or heading_column not in df.columns:
        return df

    heading_options = sorted_unique_values(df[heading_column])
    selected_headings = st.multiselect(
        "Heading filter",
        options=heading_options,
        default=heading_options[: min(len(heading_options), 4)],
    )
    if not selected_headings:
        return df
    return df[df[heading_column].isin(selected_headings)]


def render_individual_plot_tab(
    tables: dict[str, pd.DataFrame],
    filter_state: dict[str, object],
) -> None:
    """Render SF/BM/GZ/RAO/ShortTerm MPM direct comparison plots.

    이 탭은 "한두 개 case를 직접 비교"하는 화면입니다.
    실제 DB에서는 아래처럼 테이블 구조가 나뉠 수 있습니다.
    - SF/BM: X축은 길이 방향 위치, Y축은 SF 또는 BM
    - GZ: X축은 heel angle, Y축은 GZ
    - RAO: X축은 frequency, heading별/DOF별 RAO
    - ShortTerm MPM: case별 대표 결과값 비교

    테이블명과 컬럼명이 회사/해석 코드마다 조금씩 다를 수 있어서,
    src/fpso_analysis.py의 fuzzy matching 함수들이 축과 결과 컬럼을 추정합니다.
    """

    # 사용자가 보고 싶은 결과 종류를 고릅니다.
    result_type = st.selectbox("Result type", RESULT_TYPES)

    # 선택한 결과 종류와 이름/컬럼이 비슷한 테이블을 먼저 보여줍니다.
    # 매칭되는 테이블이 없으면 전체 테이블을 후보로 보여줍니다.
    table_options = get_result_type_table_options(tables, result_type)
    selected_table = st.selectbox("Result table", table_options)

    df = apply_filter_state(tables[selected_table], filter_state)
    if df.empty:
        st.warning("No rows match the current filters for this result table.")
        return

    heading_column = find_heading_column(df) if result_type == "RAO" else None
    df = render_heading_filter(df, heading_column)
    case_columns = get_case_columns(df)
    selected_cases = choose_cases_for_comparison(
        df,
        case_columns,
        key_prefix=f"{result_type}_{selected_table}",
    )
    selected_df = filter_by_case_labels(df, case_columns, selected_cases)
    if selected_df.empty:
        st.warning("Select one or two cases to compare.")
        return

    # SF/BM/GZ/RAO는 보통 물리적인 X축 컬럼이 있습니다.
    # 못 찾으면 row 순서 기반 Point 축을 임시로 만들어 그래프가 비지 않게 합니다.
    axis_column = find_axis_column(selected_df, result_type)
    if axis_column is None:
        selected_df = add_fallback_axis(selected_df)
        axis_column = "Point"

    case_exclusions = [*get_case_columns(selected_df), axis_column, heading_column]
    result_columns = get_numeric_result_columns(
        selected_df,
        exclude_columns=[column for column in case_exclusions if column is not None],
        exclude_axis_columns=True,
    )
    default_result = find_default_result_column(selected_df, result_type)
    if not result_columns:
        st.warning("No numeric result columns were found for this result table.")
        return

    y_column = st.selectbox(
        "Y-axis result",
        result_columns,
        index=get_option_index(result_columns, default_result),
    )

    plot_df = build_plot_group_column(selected_df, heading_column)
    hover_columns = [*get_case_hover_columns(plot_df), axis_column, y_column]

    # ShortTerm MPM처럼 case별 대표값 하나를 비교하는 경우는 bar chart가 읽기 쉽습니다.
    # SF/BM/GZ/RAO처럼 X축 분포가 있는 경우는 line chart가 자연스럽습니다.
    if result_type == "ShortTerm MPM" or axis_column == "Point":
        display_df = plot_df.drop_duplicates(subset=["Case"])
        figure = make_case_bar_chart(display_df, "Case", y_column)
    else:
        figure = make_case_line_chart(
            plot_df,
            x_column=axis_column,
            y_column=y_column,
            color_column="Plot Group",
            hover_columns=hover_columns,
        )
    st.plotly_chart(figure, use_container_width=True)

    with st.expander("Selected result rows", expanded=False):
        st.dataframe(plot_df, use_container_width=True, hide_index=True)
        render_csv_download(
            plot_df,
            "Download selected result rows",
            "fpso_selected_result_rows.csv",
            f"download_selected_rows_{result_type}_{selected_table}",
        )


def render_1d_trend_tabs(
    df: pd.DataFrame,
    dimension_columns: list[str],
    metric_column: str,
    color_column: str | None,
) -> None:
    """Render one trend plot per L/B/D dimension.

    여기서는 단순 선형회귀 y = a + b*x를 사용합니다.
    예를 들어 x=L, y=GM이면 "L이 커질 때 GM이 증가/감소하는 경향"과 R2를 봅니다.
    """

    tabs = st.tabs([f"{column} trend" for column in dimension_columns])
    hover_columns = [*get_case_hover_columns(df), metric_column]
    for tab, dimension_column in zip(tabs, dimension_columns):
        with tab:
            # fit_linear_regression()은 coefficients, 예측값, R2를 반환합니다.
            fit = fit_linear_regression(df, [dimension_column], metric_column)
            if fit is None:
                st.warning("Not enough rows for this trend model.")
                continue

            st.metric("R2", f"{fit['r2']:.4f}")
            trend_df = build_1d_trend_line(df, dimension_column, metric_column)
            figure = make_trend_with_line_chart(
                df=df,
                trend_df=trend_df,
                x_column=dimension_column,
                y_column=metric_column,
                color_column=color_column if color_column in df.columns else None,
                hover_columns=hover_columns,
            )
            st.plotly_chart(figure, use_container_width=True)


def render_2d_trend_panel(
    df: pd.DataFrame,
    dimension_columns: list[str],
    metric_column: str,
) -> None:
    """Render pairwise L/B, B/D, and L/D trend analysis."""

    if len(dimension_columns) < 2:
        return

    pair_options = [
        "+".join(pair)
        for pair in zip(dimension_columns, dimension_columns[1:])
    ]
    if len(dimension_columns) >= 3:
        pair_options.append(f"{dimension_columns[0]}+{dimension_columns[2]}")

    selected_pair_name = st.selectbox("2D dimension pair", pair_options)
    selected_pair = selected_pair_name.split("+")
    fit = fit_linear_regression(df, selected_pair, metric_column)
    if fit is not None:
        st.metric("2D R2", f"{fit['r2']:.4f}")

    figure = make_2d_metric_scatter(
        df=df,
        x_column=selected_pair[0],
        y_column=selected_pair[1],
        metric_column=metric_column,
        hover_columns=[*get_case_hover_columns(df), metric_column],
    )
    st.plotly_chart(figure, use_container_width=True)


def render_3d_trend_panel(
    df: pd.DataFrame,
    dimension_columns: list[str],
    metric_column: str,
) -> None:
    """Render L/B/D 3D trend analysis."""

    if len(dimension_columns) < 3:
        return

    lbd_columns = dimension_columns[:3]
    fit = fit_linear_regression(df, lbd_columns, metric_column)
    if fit is not None:
        st.metric("3D LBD R2", f"{fit['r2']:.4f}")

    figure = make_3d_metric_scatter(
        df=df,
        dimension_columns=lbd_columns,
        metric_column=metric_column,
        hover_columns=[*get_case_hover_columns(df), metric_column],
    )
    st.plotly_chart(figure, use_container_width=True)


def render_trend_tab(summary_df: pd.DataFrame, filter_state: dict[str, object]) -> None:
    """Render 1D, 2D, and 3D trend analysis with R2 values.

    이 탭의 목적:
    - L별, B별, D별 1차원 경향성 확인
    - LB, BD, LD 조합의 2차원 경향성 확인
    - LBD 전체 조합의 3차원 경향성 확인

    R2는 회귀모델이 데이터를 얼마나 잘 설명하는지 나타내는 값입니다.
    1에 가까울수록 해당 제원 조합으로 결과값을 잘 설명한다는 뜻입니다.
    """

    filtered_df = apply_filter_state(summary_df, filter_state)
    dimension_columns = [
        column
        for column in get_dimension_columns(filtered_df)
        if pd.api.types.is_numeric_dtype(filtered_df[column])
    ]
    metric_columns = get_summary_metric_columns(filtered_df)
    condition_column = filter_state["condition_column"]

    if filtered_df.empty or not dimension_columns or not metric_columns:
        st.warning("Trend analysis needs numeric dimensions and output columns.")
        return

    selected_metric = st.selectbox("Trend metric", metric_columns)
    selected_overview_metrics = st.multiselect(
        "R2 overview metrics",
        options=metric_columns,
        default=metric_columns[: min(6, len(metric_columns))],
    )

    feature_sets = get_pair_feature_sets(dimension_columns)
    r2_overview = build_r2_overview(
        filtered_df,
        selected_overview_metrics,
        feature_sets,
    )
    st.dataframe(r2_overview.round(4), use_container_width=True, hide_index=True)
    render_csv_download(
        r2_overview.round(6),
        "Download R2 overview",
        "fpso_r2_overview.csv",
        "download_r2_overview",
    )

    render_1d_trend_tabs(filtered_df, dimension_columns, selected_metric, condition_column)

    two_d_col, three_d_col = st.columns(2)
    with two_d_col:
        render_2d_trend_panel(filtered_df, dimension_columns, selected_metric)
    with three_d_col:
        render_3d_trend_panel(filtered_df, dimension_columns, selected_metric)


def render_statistics_tab(
    summary_df: pd.DataFrame,
    filter_state: dict[str, object],
) -> None:
    """Render descriptive statistics and correlation analysis.

    Statistics & Correlation 탭은 설계 판단 전 데이터 감을 잡기 위한 화면입니다.
    - describe(): 평균, 표준편차, 최소/최대 등 기본 통계량
    - corr(): 결과 컬럼 간 상관계수

    상관계수는 원인-결과를 증명하지는 않지만,
    어떤 결과들이 같이 증가/감소하는지 빠르게 파악하는 데 유용합니다.
    """

    filtered_df = apply_filter_state(summary_df, filter_state)
    metric_columns = get_summary_metric_columns(filtered_df)
    if filtered_df.empty or not metric_columns:
        st.warning("Statistics need at least one numeric output column.")
        return

    selected_metrics = st.multiselect(
        "Statistics metrics",
        options=metric_columns,
        default=metric_columns[: min(10, len(metric_columns))],
    )
    if not selected_metrics:
        return

    stats = filtered_df[selected_metrics].describe().T.round(4)
    st.dataframe(stats, use_container_width=True)
    render_csv_download(
        stats.reset_index(names="Metric"),
        "Download statistics",
        "fpso_statistics.csv",
        "download_statistics",
    )

    if len(selected_metrics) >= 2:
        correlation = filtered_df[selected_metrics].corr(numeric_only=True)
        figure = make_correlation_heatmap(correlation)
        st.plotly_chart(figure, use_container_width=True)
        render_csv_download(
            correlation.reset_index(names="Metric"),
            "Download correlation matrix",
            "fpso_correlation_matrix.csv",
            "download_correlation_matrix",
        )


def get_numeric_default_value(df: pd.DataFrame, column: str) -> float:
    """Return a stable default value for a numeric constraint input."""

    clean = df[column].dropna()
    if clean.empty:
        return 0.0
    return float(clean.median())


def render_constraints(df: pd.DataFrame, numeric_columns: list[str]) -> list[dict[str, object]]:
    """Render user-defined numeric constraints.

    Constraint는 "조건을 만족하지 못하는 case를 제거"하기 위한 입력입니다.
    예:
    - GM >= 4.0
    - Max.SF <= 허용값
    - Roll MPM <= 기준값

    반환값은 list[dict] 형태입니다.
    예:
        [
            {"column": "GM", "operator": ">=", "value": 4.0},
            {"column": "Roll MPM", "operator": "<=", "value": 1.5},
        ]
    """

    constraint_count = st.number_input(
        "Number of constraints",
        min_value=0,
        max_value=12,
        value=0,
        step=1,
    )
    constraints: list[dict[str, object]] = []

    for index in range(int(constraint_count)):
        metric_col, operator_col, value_col = st.columns([3, 1, 2])
        column = metric_col.selectbox(
            f"Constraint {index + 1} metric",
            numeric_columns,
            key=f"constraint_metric_{index}",
        )
        operator = operator_col.selectbox(
            "Operator",
            ["<=", ">=", "<", ">", "=="],
            key=f"constraint_operator_{index}",
        )
        value = value_col.number_input(
            "Value",
            value=get_numeric_default_value(df, column),
            key=f"constraint_value_{index}",
        )
        constraints.append({"column": column, "operator": operator, "value": value})

    return constraints


def render_recommended_case(recommended_df: pd.DataFrame) -> None:
    """Render the top economic case.

    recommended_df는 Pareto set을 경제성 objective 기준으로 정렬한 결과입니다.
    첫 번째 행이 현재 기준에서 가장 추천되는 case입니다.
    """

    if recommended_df.empty:
        st.warning("No feasible Pareto case was found.")
        return

    recommended_row = recommended_df.iloc[0]
    st.success(f"Recommended case: {recommended_row.get('Case', 'Case 1')}")
    st.dataframe(recommended_df.head(1), use_container_width=True, hide_index=True)


def get_default_score_direction(
    column: str,
    primary_objective_column: str,
    primary_objective_direction: str,
) -> str:
    """Choose a reasonable default direction for weighted ranking.

    Weighted ranking에서 각 objective는 min 또는 max 방향을 가져야 합니다.
    - Hull Steel Weight 같은 비용/중량은 보통 min이 좋습니다.
    - GM 같은 성능/여유는 보통 max가 좋습니다.
    기본값은 primary objective의 방향을 따르고, 나머지는 max로 둡니다.
    """

    if column == primary_objective_column:
        return primary_objective_direction
    return "max"


def render_weighted_ranking_controls(
    metric_columns: list[str],
    primary_objective_column: str,
    primary_objective_direction: str,
    performance_columns: list[str],
) -> list[dict[str, object]]:
    """Render objective direction/weight controls for explainable ranking.

    Pareto set은 "지배되지 않는 후보군"을 만드는 방법입니다.
    하지만 Pareto 후보가 여러 개 남으면 사용자는 결국 하나를 골라야 합니다.

    Weighted ranking은 그 다음 단계입니다.
    사용자가 각 objective의 방향(min/max)과 가중치(weight)를 주면,
    모든 값을 0~1 점수로 정규화한 뒤 가중 평균으로 순위를 만듭니다.
    """

    default_score_columns = list(
        dict.fromkeys([primary_objective_column, *performance_columns])
    )
    score_columns = st.multiselect(
        "Weighted score objectives",
        options=metric_columns,
        default=default_score_columns,
    )

    objective_specs: list[dict[str, object]] = []
    for column in score_columns:
        direction_col, weight_col = st.columns([1, 1])
        direction = direction_col.selectbox(
            f"{column} direction",
            ["min", "max"],
            index=0
            if get_default_score_direction(
                column,
                primary_objective_column,
                primary_objective_direction,
            )
            == "min"
            else 1,
            key=f"score_direction_{column}",
        )
        default_weight = 3.0 if column == primary_objective_column else 1.0
        weight = weight_col.number_input(
            f"{column} weight",
            min_value=0.0,
            max_value=20.0,
            value=default_weight,
            step=0.5,
            key=f"score_weight_{column}",
        )
        objective_specs.append(
            {
                "column": column,
                "direction": direction,
                "weight": weight,
            }
        )

    return objective_specs


def render_weighted_ranking(
    feasible_df: pd.DataFrame,
    pareto_df: pd.DataFrame,
    metric_columns: list[str],
    primary_objective_column: str,
    primary_objective_direction: str,
    performance_columns: list[str],
) -> None:
    """Render an optional weighted ranking over feasible or Pareto cases.

    rank_only_pareto=True이면 Pareto set 안에서만 weighted score를 계산합니다.
    이 방식이 기본값인 이유:
    - 먼저 constraint와 Pareto로 명백히 불리한 case를 제거합니다.
    - 그 다음 남은 후보 안에서 경제성/성능 가중치를 비교합니다.
    """

    with st.expander("Weighted ranking", expanded=True):
        rank_only_pareto = st.checkbox("Rank Pareto set only", value=True)
        ranking_base = pareto_df if rank_only_pareto and not pareto_df.empty else feasible_df

        objective_specs = render_weighted_ranking_controls(
            metric_columns,
            primary_objective_column,
            primary_objective_direction,
            performance_columns,
        )
        scored_df = build_weighted_score_table(ranking_base, objective_specs)

        if scored_df.empty:
            st.warning("No cases are available for weighted ranking.")
            return

        top_case = scored_df.iloc[0]
        st.info(
            f"Weighted-score recommendation: {top_case.get('Case', 'Case 1')} "
            f"(score={top_case['Weighted Score']:.3f})"
        )
        st.dataframe(scored_df.head(20), use_container_width=True, hide_index=True)
        render_csv_download(
            scored_df,
            "Download weighted ranking",
            "fpso_weighted_ranking.csv",
            "download_weighted_ranking",
        )


def render_optimization_tab(
    summary_df: pd.DataFrame,
    filter_state: dict[str, object],
) -> None:
    """Render constraint filtering, Pareto set, and economic recommendation.

    Optimal Dimensions 탭의 계산 순서:

    1. 공통 필터 적용
       - 사이드바의 L/B/D/LC 필터를 먼저 적용합니다.

    2. Constraint 적용
       - 사용자가 입력한 GM, SF, BM, MPM 등의 제한조건으로 case를 제거합니다.

    3. Pareto set 계산
       - 어떤 case가 다른 case보다 모든 objective에서 같거나 좋고,
         적어도 하나의 objective에서 더 좋으면 상대 case는 제거됩니다.

    4. Primary economic objective로 정렬
       - Hull Steel Weight가 있으면 기본적으로 최소화 대상입니다.

    5. Weighted ranking
       - Pareto 후보가 여러 개 남았을 때 최종 추천 순위를 설명하기 위한 점수입니다.
    """

    filtered_df = apply_filter_state(summary_df, filter_state)
    metric_columns = get_summary_metric_columns(filtered_df)
    dimension_columns = get_dimension_columns(filtered_df)
    case_columns = get_case_columns(filtered_df)
    hover_columns = [*get_case_hover_columns(filtered_df), "Case"]

    if filtered_df.empty or not metric_columns:
        st.warning("Optimization needs feasible rows and numeric output columns.")
        return

    # 사용자가 입력한 constraint를 읽고 feasible case만 남깁니다.
    constraints = render_constraints(filtered_df, metric_columns)
    feasible_df = apply_constraints(filtered_df, constraints)

    # 최적화 결과표에서 case를 사람이 읽을 수 있도록 "L=... | B=... | LC=..." 형태로 붙입니다.
    feasible_df = add_case_label(feasible_df, case_columns)

    st.metric("Feasible cases", len(feasible_df))
    if feasible_df.empty:
        st.warning("All cases were removed by the current constraints.")
        return

    # Hull Steel Weight 계열 컬럼이 있으면 경제성 objective 기본값으로 잡습니다.
    # 실제 컬럼명이 조금 달라도 후보 리스트에서 자동 탐색합니다.
    hull_weight_column = find_hull_weight_column(metric_columns)
    objective_column = st.selectbox(
        "Primary economic objective",
        metric_columns,
        index=get_option_index(metric_columns, hull_weight_column),
    )
    objective_direction = st.selectbox(
        "Primary objective direction",
        ["min", "max"],
        index=0 if objective_column == hull_weight_column else 0,
    )
    performance_columns = st.multiselect(
        "Additional Pareto objectives to maximize",
        options=[column for column in metric_columns if column != objective_column],
        default=[],
    )

    # Pareto 계산에 사용할 objective 목록입니다.
    # 첫 번째는 경제성 objective이고, 나머지는 사용자가 "최대화하고 싶은 성능"으로 고른 컬럼입니다.
    objective_columns = [objective_column, *performance_columns]
    directions = [objective_direction, *["max" for _ in performance_columns]]
    pareto_mask = build_pareto_mask(feasible_df, objective_columns, directions)
    feasible_df = feasible_df.copy()
    feasible_df["Pareto"] = pareto_mask

    pareto_df = feasible_df[feasible_df["Pareto"]].copy()
    recommended_df = sort_optimal_cases(
        pareto_df,
        objective_column,
        objective_direction,
    )
    render_recommended_case(recommended_df)
    render_csv_download(
        feasible_df,
        "Download feasible cases",
        "fpso_feasible_cases.csv",
        "download_feasible_cases",
    )
    render_csv_download(
        pareto_df,
        "Download Pareto set",
        "fpso_pareto_set.csv",
        "download_pareto_set",
    )

    y_options = performance_columns or [
        column for column in [*dimension_columns, *metric_columns] if column != objective_column
    ]
    if y_options:
        y_column = st.selectbox("Pareto chart Y-axis", y_options)
        figure = make_pareto_scatter(
            feasible_df,
            x_column=objective_column,
            y_column=y_column,
            pareto_column="Pareto",
            hover_columns=[*hover_columns, *objective_columns, y_column],
        )
        st.plotly_chart(figure, use_container_width=True)

    render_weighted_ranking(
        feasible_df=feasible_df,
        pareto_df=pareto_df,
        metric_columns=metric_columns,
        primary_objective_column=objective_column,
        primary_objective_direction=objective_direction,
        performance_columns=performance_columns,
    )

    st.dataframe(
        recommended_df,
        use_container_width=True,
        hide_index=True,
    )
    render_csv_download(
        recommended_df,
        "Download recommended Pareto ranking",
        "fpso_recommended_pareto_ranking.csv",
        "download_recommended_pareto_ranking",
    )


def main() -> None:
    """Run the Streamlit dashboard.

    Streamlit은 이 파일을 위에서 아래로 실행합니다.
    하지만 실제 앱 흐름은 main() 안에 모아 두었습니다.
    그래서 전체 동작을 이해하고 싶으면 main()부터 읽는 것이 가장 쉽습니다.
    """

    configure_page()
    render_title()

    # 1. 사용자가 볼 SQLite DB 파일을 결정합니다.
    db_path = get_database_path_from_sidebar()
    stop_if_database_missing(db_path)

    # 2. DB 수정 시간을 캐시 키로 사용합니다.
    #    DB 파일이 새로 생성되거나 덮어써지면 캐시가 갱신됩니다.
    db_mtime_ns = get_file_mtime_ns(db_path)

    table_names = get_cached_table_names(str(db_path), db_mtime_ns)
    if not table_names:
        st.error("No user tables were found in the selected DB.")
        st.stop()

    # 3. DB 안의 모든 사용자 테이블을 읽습니다.
    tables = get_cached_database_tables(str(db_path), db_mtime_ns)
    render_table_overview(tables)

    # 4. Summary/Trend/Statistics/Optimization의 기준이 되는 대표 테이블을 고릅니다.
    summary_table = select_summary_table(tables)
    summary_df = tables[summary_table]

    # 5. 사이드바 공통 필터 상태를 만듭니다.
    filter_state = build_filter_state(summary_df)

    # 6. 사용자가 요청한 5개 주요 화면을 탭으로 나눕니다.
    tabs = st.tabs(
        [
            "Summary",
            "Individual Plots",
            "Trend Analysis",
            "Statistics & Correlation",
            "Optimal Dimensions",
        ]
    )

    with tabs[0]:
        render_summary_tab(tables, summary_df, filter_state)
    with tabs[1]:
        render_individual_plot_tab(tables, filter_state)
    with tabs[2]:
        render_trend_tab(summary_df, filter_state)
    with tabs[3]:
        render_statistics_tab(summary_df, filter_state)
    with tabs[4]:
        render_optimization_tab(summary_df, filter_state)


if __name__ == "__main__":
    main()
