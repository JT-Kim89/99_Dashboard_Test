"""Plotly chart helpers.

Streamlit은 st.line_chart 같은 기본 차트도 제공하지만,
범례/hover/마커를 조금 더 쉽게 다루기 위해 Plotly를 사용합니다.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure


def get_trend_group_columns(
    x_column: str,
    color_column: str | None,
) -> list[str]:
    """평균 추세선을 계산할 때 사용할 그룹 컬럼을 정합니다."""

    if color_column is None:
        return [x_column]
    return [x_column, color_column]


def summarize_metric_for_trend(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    color_column: str | None,
) -> pd.DataFrame:
    """원자료를 제원/조건별 평균값으로 요약합니다."""

    group_columns = get_trend_group_columns(x_column, color_column)
    summary = (
        df.groupby(group_columns, dropna=False)[y_column]
        .agg(mean_value="mean", case_count="count")
        .reset_index()
    )
    return summary.sort_values(group_columns)


def make_metric_trend_chart(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    color_column: str | None,
    hover_columns: list[str],
) -> Figure:
    """제원 컬럼별 metric 평균 추세를 선+점 그래프로 만듭니다."""

    plot_df = summarize_metric_for_trend(df, x_column, y_column, color_column)
    hover_data = [column for column in hover_columns if column in plot_df.columns]
    hover_data.append("case_count")

    figure = px.line(
        plot_df,
        x=x_column,
        y="mean_value",
        color=color_column,
        markers=True,
        hover_data=hover_data,
    )
    figure.update_layout(
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        legend_title_text=color_column or "",
        xaxis_title=x_column,
        yaxis_title=f"{y_column} mean",
    )
    return figure


def make_metric_box_chart(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    color_column: str | None,
) -> Figure:
    """같은 제원 값 안에서 metric 분포를 비교하는 box plot을 만듭니다."""

    plot_df = df.copy()
    plot_df[x_column] = plot_df[x_column].astype(str)

    figure = px.box(
        plot_df,
        x=x_column,
        y=y_column,
        color=color_column,
        points="all",
    )
    figure.update_layout(
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        legend_title_text=color_column or "",
        xaxis_title=x_column,
        yaxis_title=y_column,
    )
    return figure
