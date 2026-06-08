"""Plotly chart helpers.

이 파일은 그래프를 만드는 함수만 모아 둔 곳입니다.

초보자용 설명:
- app.py에서 직접 px.scatter(), px.line() 같은 Plotly 코드를 길게 쓰면
  화면 로직과 그래프 옵션이 섞여 읽기 어려워집니다.
- 그래서 "어떤 차트를 만들지"는 app.py가 결정하고,
  "그 차트를 Plotly로 어떻게 그릴지"는 이 파일이 담당합니다.

Plotly 기본 개념:
- px.scatter(): 산점도
- px.line(): 선 그래프
- px.bar(): 막대 그래프
- px.box(): box plot
- px.imshow(): heatmap
- px.scatter_3d(): 3D 산점도

모든 함수는 Plotly Figure를 반환하고, app.py에서 st.plotly_chart()로 화면에 표시합니다.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.graph_objects import Figure


def get_trend_group_columns(
    x_column: str,
    color_column: str | None,
) -> list[str]:
    """평균 추세선을 계산할 때 사용할 그룹 컬럼을 정합니다.

    color_column이 있으면 Loading Condition별로 선을 따로 그립니다.
    예:
    - x_column="L", color_column="LC"
      -> L과 LC 조합별 평균을 계산합니다.
    """

    if color_column is None:
        return [x_column]
    return [x_column, color_column]


def summarize_metric_for_trend(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    color_column: str | None,
) -> pd.DataFrame:
    """원자료를 제원/조건별 평균값으로 요약합니다.

    같은 L 값에 여러 case가 있을 수 있으므로 평균값을 먼저 계산합니다.
    case_count는 hover에 표시해서 평균이 몇 개 행에서 나온 값인지 알 수 있게 합니다.
    """

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


def make_summary_max_scatter(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    max_index: object | None,
    color_column: str | None,
    hover_columns: list[str],
) -> Figure:
    """Create a summary scatter plot with the global max case highlighted in red.

    Summary 탭에서 사용하는 그래프입니다.
    - 일반 case는 회색 점
    - 선택 metric의 최대값 case는 빨간 점
    - hover에는 L/B/D/LC와 metric 값이 표시됩니다.
    """

    plot_df = df.copy()

    # Plotly color에 사용할 임시 컬럼입니다.
    # 모든 행은 기본적으로 Case이고, 최대값 행만 Max로 바꿉니다.
    plot_df["_highlight"] = "Case"
    if max_index is not None and max_index in plot_df.index:
        plot_df.loc[max_index, "_highlight"] = "Max"

    figure = px.scatter(
        plot_df,
        x=x_column,
        y=y_column,
        color="_highlight",
        symbol=color_column,
        hover_data=[column for column in hover_columns if column in plot_df.columns],
        color_discrete_map={"Case": "#9ca3af", "Max": "#ef4444"},
    )
    figure.update_traces(marker={"size": 9, "line": {"width": 0.5, "color": "#111827"}})
    figure.update_layout(
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        legend_title_text="",
        xaxis_title=x_column,
        yaxis_title=y_column,
    )
    return figure


def make_case_line_chart(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    color_column: str,
    hover_columns: list[str],
) -> Figure:
    """Create a line chart for one or more selected cases.

    SF/BM/GZ/RAO처럼 x축을 따라 값이 변하는 결과를 비교할 때 씁니다.
    color_column은 보통 Case 또는 Case+Heading 조합입니다.
    """

    # 선 그래프는 x축 순서가 중요하므로 case와 x축 기준으로 정렬합니다.
    figure = px.line(
        df.sort_values([color_column, x_column]),
        x=x_column,
        y=y_column,
        color=color_column,
        markers=True,
        hover_data=[column for column in hover_columns if column in df.columns],
    )
    figure.update_layout(
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        legend_title_text="Case",
        xaxis_title=x_column,
        yaxis_title=y_column,
    )
    return figure


def make_case_bar_chart(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    color_column: str | None = None,
) -> Figure:
    """Create a compact bar chart for selected cases or summary rows.

    ShortTerm MPM처럼 case당 대표값 하나를 비교할 때는 line보다 bar가 읽기 쉽습니다.
    """

    figure = px.bar(
        df,
        x=x_column,
        y=y_column,
        color=color_column,
        hover_data=df.columns,
    )
    figure.update_layout(
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        legend_title_text=color_column or "",
        xaxis_title=x_column,
        yaxis_title=y_column,
    )
    return figure


def make_trend_with_line_chart(
    df: pd.DataFrame,
    trend_df: pd.DataFrame,
    x_column: str,
    y_column: str,
    color_column: str | None,
    hover_columns: list[str],
) -> Figure:
    """Create a 1D scatter plot with a fitted trend line.

    Trend Analysis 탭에서 L별/B별/D별 경향성을 볼 때 사용합니다.
    - 원자료는 scatter 점으로 표시
    - 회귀분석으로 계산한 trend line은 빨간 선으로 표시
    """

    figure = px.scatter(
        df,
        x=x_column,
        y=y_column,
        color=color_column,
        hover_data=[column for column in hover_columns if column in df.columns],
    )

    # trend_df는 src/fpso_analysis.py의 build_1d_trend_line()에서 만든 값입니다.
    # 회귀분석에 필요한 데이터가 부족하면 빈 DataFrame이 올 수 있습니다.
    if not trend_df.empty:
        figure.add_trace(
            go.Scatter(
                x=trend_df[x_column],
                y=trend_df["Trend"],
                mode="lines",
                name="Trend line",
                line={"color": "#ef4444", "width": 3},
            )
        )

    figure.update_layout(
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        legend_title_text=color_column or "",
        xaxis_title=x_column,
        yaxis_title=y_column,
    )
    return figure


def make_2d_metric_scatter(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    metric_column: str,
    hover_columns: list[str],
) -> Figure:
    """Create a 2D dimension scatter colored by the selected metric.

    예:
    - x=L, y=B, color=GM
    - x=B, y=D, color=Roll MPM

    색이 진하거나 밝은 위치를 보면 어떤 제원 조합에서 결과가 커지는지 볼 수 있습니다.
    """

    figure = px.scatter(
        df,
        x=x_column,
        y=y_column,
        color=metric_column,
        hover_data=[column for column in hover_columns if column in df.columns],
        color_continuous_scale="Viridis",
    )
    figure.update_layout(
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        xaxis_title=x_column,
        yaxis_title=y_column,
    )
    return figure


def make_3d_metric_scatter(
    df: pd.DataFrame,
    dimension_columns: list[str],
    metric_column: str,
    hover_columns: list[str],
) -> Figure:
    """Create a 3D L/B/D scatter colored by the selected metric.

    L, B, D 세 제원을 동시에 봐야 할 때 사용합니다.
    점의 위치는 제원 조합이고, 색은 선택한 output metric입니다.
    """

    figure = px.scatter_3d(
        df,
        x=dimension_columns[0],
        y=dimension_columns[1],
        z=dimension_columns[2],
        color=metric_column,
        hover_data=[column for column in hover_columns if column in df.columns],
        color_continuous_scale="Viridis",
    )
    figure.update_layout(
        margin={"l": 0, "r": 0, "t": 30, "b": 0},
        scene={
            "xaxis_title": dimension_columns[0],
            "yaxis_title": dimension_columns[1],
            "zaxis_title": dimension_columns[2],
        },
    )
    return figure


def make_correlation_heatmap(correlation: pd.DataFrame) -> Figure:
    """Create a correlation heatmap.

    correlation DataFrame은 pandas corr() 결과입니다.
    값의 범위는 -1~1입니다.
    - 1에 가까우면 같이 증가
    - -1에 가까우면 하나가 증가할 때 다른 하나는 감소
    - 0에 가까우면 선형 관계가 약함
    """

    figure = px.imshow(
        correlation,
        text_auto=".2f",
        zmin=-1,
        zmax=1,
        color_continuous_scale="RdBu_r",
        aspect="auto",
    )
    figure.update_layout(margin={"l": 20, "r": 20, "t": 30, "b": 20})
    return figure


def make_pareto_scatter(
    df: pd.DataFrame,
    x_column: str,
    y_column: str,
    pareto_column: str,
    hover_columns: list[str],
) -> Figure:
    """Create a scatter plot that separates Pareto cases from feasible cases.

    Optimal Dimensions 탭에서 사용합니다.
    - 회색 점: constraint는 통과했지만 Pareto set은 아닌 feasible case
    - 빨간 점: Pareto-efficient case
    """

    figure = px.scatter(
        df,
        x=x_column,
        y=y_column,
        color=pareto_column,
        hover_data=[column for column in hover_columns if column in df.columns],
        color_discrete_map={True: "#ef4444", False: "#9ca3af"},
    )
    figure.update_traces(marker={"size": 9, "line": {"width": 0.5, "color": "#111827"}})
    figure.update_layout(
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        legend_title_text="Pareto",
        xaxis_title=x_column,
        yaxis_title=y_column,
    )
    return figure
