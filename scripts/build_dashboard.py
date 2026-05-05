#!/usr/bin/env python3
"""导出考研学习驾驶舱 HTML。

用法:
  python3 build_dashboard.py [OBSIDIAN_ROOT] [--output path] [--today YYYY-MM-DD]

特点:
- 只读取现有档案、日志、错题卡、知识地图和报告
- 输出一个自包含 HTML，可直接通过 file:// 或双击打开
- stdout 返回 JSON payload，便于后续调试或扩展
- 数据收集与归一化在 dashboard_payload,本文件只负责渲染层。
"""
import argparse
import html
import json
from datetime import date
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from constants import PLAN_SUBJECTS, SCORE_SUBJECTS, SUBJECT_META
from dashboard_payload import build_payload, format_number
from env_util import atomic_write, resolve_obsidian_root
from score_record_lib import format_optional_number, top_weakness_from_408_record
from study_ops import parse_today

SUBJECT_BY_TAB_ID = {meta["tab_id"]: subject for subject, meta in SUBJECT_META.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出考研学习驾驶舱 HTML")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("--output", help="输出 HTML 文件路径；默认写到 OBSIDIAN_ROOT/可视化面板/index.html")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    return parser.parse_args()


def resolve_output_path(obsidian_root: Path, output_arg: Optional[str]) -> Path:
    if not output_arg:
        return obsidian_root / "可视化面板" / "index.html"

    output_path = Path(output_arg).expanduser()
    if output_path.suffix.lower() == ".html":
        return output_path
    return output_path / "index.html"


def e(value: object) -> str:
    return html.escape(str(value))


def render_metric_card(title: str, value: str, caption: str, tone: str) -> str:
    return (
        f'<article class="metric-card tone-{tone}">'
        f'<div class="metric-title">{e(title)}</div>'
        f'<div class="metric-value">{e(value)}</div>'
        f'<div class="metric-caption">{e(caption)}</div>'
        "</article>"
    )


def render_empty_state(message: str) -> str:
    return f'<div class="empty-state">{e(message)}</div>'


def render_bar_rows(rows: Sequence[Mapping[str, object]], empty_message: str) -> str:
    if not rows or all(int(row.get("value", 0)) == 0 for row in rows):
        return render_empty_state(empty_message)

    max_value = max(int(row.get("value", 0)) for row in rows) or 1
    parts = ['<div class="bar-list">']
    for row in rows:
        value = int(row.get("value", 0))
        ratio = value / max_value if max_value else 0
        parts.append(
            '<div class="bar-row">'
            f'<div class="bar-label">{e(row.get("label", ""))}</div>'
            '<div class="bar-track">'
            f'<div class="bar-fill" style="width: {ratio * 100:.1f}%"></div>'
            "</div>"
            f'<div class="bar-value">{value}</div>'
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)

def build_axis_ticks(min_value: float, max_value: float, step: float) -> List[float]:
    """按固定步长生成轴刻度,保证 min/max 都被覆盖。

    与"均分 N 段"的 linspace 不同:这里语义是"每隔 step 一个刻度"。
    当 (max - min) 不能被 step 整除时,最后一个刻度会被钳制为 max,
    避免生成 [0, 32.5, 65, 97.5, 130] 这类非整数刻度。
    """
    if step <= 0 or max_value <= min_value:
        return [min_value]
    ticks: List[float] = []
    value = min_value
    while value < max_value - 1e-9:
        ticks.append(value)
        value += step
    ticks.append(max_value)
    return ticks


def build_x_tick_labels(labels: Sequence[str]) -> List[Tuple[int, str]]:
    """从一串日期标签中均匀挑出 3-6 个用于 X 轴显示。

    保证首尾被选中,中间均匀采样,标签数随序列长度自适应:
    - 6 条以内全显示
    - 7-12 条显示 4 个
    - 13-24 条显示 5 个
    - 25 条以上显示 6 个
    """
    n = len(labels)
    if n == 0:
        return []
    if n <= 6:
        return list(enumerate(labels))
    if n <= 12:
        target = 4
    elif n <= 24:
        target = 5
    else:
        target = 6

    indexes: List[int] = []
    for k in range(target):
        index = round(k * (n - 1) / (target - 1))
        if index not in indexes:
            indexes.append(index)
    return [(index, labels[index]) for index in indexes]


def render_line_chart(
    points: Sequence[Mapping[str, object]],
    color: str,
    empty_message: str,
    y_min: float,
    y_max: float,
    y_step: float,
) -> str:
    valid_points = [point for point in points if isinstance(point.get("total_score"), (int, float))]
    if not valid_points:
        return render_empty_state(empty_message)

    width = 720
    height = 280
    pad_x = 48
    pad_y = 24
    bottom_pad = 54
    inner_width = width - pad_x * 2
    inner_height = height - pad_y - bottom_pad
    labels = [point["exam_date"] for point in valid_points]

    def x_at(index: int) -> float:
        if len(valid_points) == 1:
            return width / 2
        return pad_x + inner_width * index / (len(valid_points) - 1)

    def y_at(value: float) -> float:
        ratio = (value - y_min) / (y_max - y_min)
        return pad_y + inner_height * (1 - ratio)

    polyline = " ".join(f"{x_at(index):.1f},{y_at(float(point['total_score'])):.1f}" for index, point in enumerate(valid_points))
    circles = []
    for index, point in enumerate(valid_points):
        x = x_at(index)
        y = y_at(float(point["total_score"]))
        tooltip = f'{point["exam_date"]} {point["paper_label"]} {format_number(point["total_score"])}'
        circles.append(
            f'<circle class="tooltip-point" data-tooltip="{e(tooltip)}" cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}"><title>{e(tooltip)}</title></circle>'
        )

    y_grid = []
    for tick in build_axis_ticks(y_min, y_max, y_step):
        y = y_at(tick)
        y_grid.append(f'<line x1="{pad_x}" y1="{y:.1f}" x2="{width - pad_x}" y2="{y:.1f}" stroke="rgba(20,33,61,0.08)" stroke-width="1" />')
        y_grid.append(f'<text x="{pad_x - 8}" y="{y + 4:.1f}" fill="#5f6b7a" font-size="11" text-anchor="end">{e(format_number(tick))}</text>')

    x_labels = []
    baseline_y = height - bottom_pad
    for index, label in build_x_tick_labels(labels):
        x = x_at(index)
        x_labels.append(f'<line x1="{x:.1f}" y1="{baseline_y}" x2="{x:.1f}" y2="{baseline_y + 4}" stroke="rgba(20,33,61,0.16)" stroke-width="1" />')
        x_labels.append(f'<text x="{x:.1f}" y="{height - 18}" fill="#5f6b7a" font-size="11" text-anchor="middle">{e(label)}</text>')
    return (
        f'<svg class="trend-chart" viewBox="0 0 {width} {height}" role="img" aria-label="成绩趋势图">'
        + "".join(y_grid)
        + f'<line x1="{pad_x}" y1="{baseline_y}" x2="{width - pad_x}" y2="{baseline_y}" stroke="rgba(20,33,61,0.16)" stroke-width="1" />'
        + f'<line x1="{pad_x}" y1="{pad_y}" x2="{pad_x}" y2="{baseline_y}" stroke="rgba(20,33,61,0.16)" stroke-width="1" />'
        f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{polyline}" />'
        + "".join(circles)
        + "".join(x_labels)
        + f'<text x="{width / 2:.1f}" y="{height - 2}" fill="#5f6b7a" font-size="11" text-anchor="middle">日期</text>'
        + f'<text x="16" y="{pad_y + inner_height / 2:.1f}" fill="#5f6b7a" font-size="11" text-anchor="middle" transform="rotate(-90 16 {pad_y + inner_height / 2:.1f})">分数</text>'
        + "</svg>"
    )


def render_multi_line_chart(
    series: Sequence[Mapping[str, object]],
    empty_message: str,
    y_min: float,
    y_max: float,
    y_step: float,
) -> str:
    dated_scores: Dict[str, Dict[str, float]] = {}
    for item in series:
        for point in item["points"]:
            dated_scores.setdefault(point["date"], {})[item["subject"]] = float(point["score"])
    all_dates = sorted(dated_scores)
    if not all_dates:
        return render_empty_state(empty_message)

    width = 720
    height = 300
    pad_x = 52
    pad_y = 24
    bottom_pad = 54
    inner_width = width - pad_x * 2
    inner_height = height - pad_y - bottom_pad

    date_to_index = {day: index for index, day in enumerate(all_dates)}

    def x_at(day: str) -> float:
        if len(all_dates) == 1:
            return width / 2
        return pad_x + inner_width * date_to_index[day] / (len(all_dates) - 1)

    def y_at(value: float) -> float:
        ratio = (value - y_min) / (y_max - y_min)
        return pad_y + inner_height * (1 - ratio)

    paths = []
    circles = []
    legends = []
    for item in series:
        points = item["points"]
        if not points:
            continue
        polyline = " ".join(f"{x_at(point['date']):.1f},{y_at(float(point['score'])):.1f}" for point in points)
        paths.append(f'<polyline fill="none" stroke="{item["color"]}" stroke-width="3" points="{polyline}" />')
        legends.append(f'<span class="legend-pill"><span class="legend-dot" style="background:{item["color"]}"></span>{e(item["subject"])}</span>')
        for point in points:
            x = x_at(point["date"])
            y = y_at(float(point["score"]))
            tooltip = f'{item["subject"]} {point["date"]} {point["paper_label"]} {format_number(point["score"])}'
            circles.append(
                f'<circle class="tooltip-point" data-tooltip="{e(tooltip)}" cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{item["color"]}"><title>{e(tooltip)}</title></circle>'
            )

    y_grid = []
    for tick in build_axis_ticks(y_min, y_max, y_step):
        y = y_at(tick)
        y_grid.append(f'<line x1="{pad_x}" y1="{y:.1f}" x2="{width - pad_x}" y2="{y:.1f}" stroke="rgba(20,33,61,0.08)" stroke-width="1" />')
        y_grid.append(f'<text x="{pad_x - 8}" y="{y + 4:.1f}" fill="#5f6b7a" font-size="11" text-anchor="end">{e(format_number(tick))}</text>')
    baseline_y = height - bottom_pad
    x_labels = []
    for index, label in build_x_tick_labels(all_dates):
        x = x_at(label)
        x_labels.append(f'<line x1="{x:.1f}" y1="{baseline_y}" x2="{x:.1f}" y2="{baseline_y + 4}" stroke="rgba(20,33,61,0.16)" stroke-width="1" />')
        x_labels.append(f'<text x="{x:.1f}" y="{height - 18}" fill="#5f6b7a" font-size="11" text-anchor="middle">{e(label)}</text>')

    svg = (
        f'<svg class="trend-chart" viewBox="0 0 {width} {height}" role="img" aria-label="四科总模考趋势图">'
        + "".join(y_grid)
        + f'<line x1="{pad_x}" y1="{baseline_y}" x2="{width - pad_x}" y2="{baseline_y}" stroke="rgba(20,33,61,0.16)" stroke-width="1" />'
        + f'<line x1="{pad_x}" y1="{pad_y}" x2="{pad_x}" y2="{baseline_y}" stroke="rgba(20,33,61,0.16)" stroke-width="1" />'
        + "".join(paths)
        + "".join(circles)
        + "".join(x_labels)
        + f'<text x="{width / 2:.1f}" y="{height - 2}" fill="#5f6b7a" font-size="11" text-anchor="middle">日期</text>'
        + f'<text x="18" y="{pad_y + inner_height / 2:.1f}" fill="#5f6b7a" font-size="11" text-anchor="middle" transform="rotate(-90 18 {pad_y + inner_height / 2:.1f})">分数</text>'
        + "</svg>"
    )
    return '<div class="chart-with-legend">' + svg + '<div class="chart-legend">' + "".join(legends) + "</div></div>"


def render_recent_score_records(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return render_empty_state("还没有卷子级成绩记录。")
    parts = [
        '<table class="score-table"><thead><tr><th>科目</th><th>日期</th><th>卷型</th><th>卷子</th><th>总分</th></tr></thead><tbody>'
    ]
    for row in rows:
        parts.append(
            f"<tr><td>{e(row['subject'])}</td><td>{e(row['date'])}</td><td>{e(row['paper_type'])}</td><td>{e(row['paper'])}</td><td>{e(format_number(row['total_score']))}</td></tr>"
        )
    parts.append("</tbody></table>")
    return "".join(parts)


def render_total_score_panel(score_trends: Mapping[str, object]) -> str:
    chart = render_line_chart(
        score_trends["total"]["points"],
        "#8b5e34",
        "还没有四科完整模考总分趋势数据。",
        0.0,
        500.0,
        100.0,
    )
    recent_rows = [
        {
            "subject": "总分",
            "date": row["date"],
            "paper_type": row["paper_type"],
            "paper": row["paper_label"],
            "total_score": row["total_score"],
        }
        for row in score_trends["total"]["recent_rows"]
    ]
    return (
        '<div class="panel-grid">'
        f'<div class="mini-panel"><h3>总分趋势</h3>{chart}</div>'
        f'<div class="mini-panel"><h3>最近完整模考</h3>{render_recent_score_records(recent_rows)}</div>'
        '</div>'
    )


def render_politics_panel(score_trends: Mapping[str, object]) -> str:
    politics = score_trends["politics"]
    meta = SUBJECT_META["政治"]
    chart = render_line_chart(
        politics["points"],
        meta["color"],
        "还没有政治套卷趋势数据。",
        0.0,
        meta["total_score"],
        meta["y_step"],
    )
    fallback_note = ""
    if politics.get("fallback_used"):
        fallback_note = (
            '<p class="lede" style="margin-top: 0;">'
            '当前显示来自联合模考表的政治分数。要单独追踪肖四肖八等政治套卷,'
            '可用 <code>record_paper_score.py 政治 ...</code> 录入。'
            '</p>'
        )
    return (
        f'{fallback_note}'
        '<div class="panel-grid">'
        f'<div class="mini-panel"><h3>政治总分趋势</h3>{chart}</div>'
        f'<div class="mini-panel"><h3>最近政治成绩</h3>{render_subject_score_table("politics", politics["recent_rows"])}</div>'
        '</div>'
    )


def render_math_breakdown_rows(points: Sequence[Mapping[str, object]]) -> str:
    rows = [point for point in points if point.get("score_objective") is not None or point.get("score_big") is not None]
    if not rows:
        return render_empty_state("当前没有数学一的选填/大题细分得分。")
    parts = ['<div class="breakdown-list">']
    for point in rows:
        objective = point.get("score_objective") or 0
        big = point.get("score_big") or 0
        total = objective + big or point["total_score"] or 1
        parts.append(
            '<article class="breakdown-card">'
            f'<div class="breakdown-head"><strong>{e(point["paper_label"])}</strong><span>{e(point["exam_date"])}</span></div>'
            '<div class="stack-track">'
            f'<div class="stack-seg seg-objective" style="width:{objective / total * 100:.1f}%"></div>'
            f'<div class="stack-seg seg-big" style="width:{big / total * 100:.1f}%"></div>'
            '</div>'
            f'<div class="breakdown-meta">选填 {e(format_optional_number(point.get("score_objective")) or "-")} · 大题 {e(format_optional_number(point.get("score_big")) or "-")} · 总分 {e(format_number(point["total_score"]))}</div>'
            '</article>'
        )
    parts.append("</div>")
    return "".join(parts)


def render_408_metric_rows(points: Sequence[Mapping[str, object]], metric_prefix: str) -> str:
    labels = [("DS", "ds"), ("CO", "co"), ("OS", "os"), ("CN", "cn")]
    if metric_prefix == "score":
        choice_prefix = "score_choice_"
        big_prefix = "score_big_"
        empty_message = "当前没有 408 的实际得分细分。"
    else:
        choice_prefix = "loss_choice_"
        big_prefix = "loss_big_"
        empty_message = "当前没有 408 的失分/错题数细分。"

    rows = []
    for point in points:
        if any(point.get(f"{choice_prefix}{suffix}") is not None for _, suffix in labels) or any(point.get(f"{big_prefix}{suffix}") is not None for _, suffix in labels):
            rows.append(point)
    if not rows:
        return render_empty_state(empty_message)

    parts = ['<div class="breakdown-list">']
    for point in rows:
        choice_text = " / ".join(
            f"{label} {format_optional_number(point.get(f'{choice_prefix}{suffix}')) or '-'}"
            for label, suffix in labels
        )
        big_text = " / ".join(
            f"{label} {format_optional_number(point.get(f'{big_prefix}{suffix}')) or '-'}"
            for label, suffix in labels
        )
        parts.append(
            '<article class="breakdown-card">'
            f'<div class="breakdown-head"><strong>{e(point["paper_label"])}</strong><span>{e(point["exam_date"])}</span></div>'
            f'<div class="breakdown-meta">选择题：{e(choice_text)}</div>'
            f'<div class="breakdown-meta">大题：{e(big_text)}</div>'
            f'<div class="breakdown-meta">总分 {e(format_number(point["total_score"]))}</div>'
            '</article>'
        )
    parts.append("</div>")
    return "".join(parts)


def render_english_breakdown_rows(points: Sequence[Mapping[str, object]]) -> str:
    rows = [
        point for point in points
        if any(point.get(field) is not None for field in ("score_cloze", "score_reading", "score_new_type", "score_translation", "score_short_essay", "score_long_essay"))
    ]
    if not rows:
        return render_empty_state("当前没有英语一的六板块细分得分。")
    parts = ['<div class="breakdown-list">']
    for point in rows:
        detail = " / ".join([
            f"完形 {format_optional_number(point.get('score_cloze')) or '-'}",
            f"阅读 {format_optional_number(point.get('score_reading')) or '-'}",
            f"新题型 {format_optional_number(point.get('score_new_type')) or '-'}",
            f"翻译 {format_optional_number(point.get('score_translation')) or '-'}",
            f"小作文 {format_optional_number(point.get('score_short_essay')) or '-'}",
            f"大作文 {format_optional_number(point.get('score_long_essay')) or '-'}",
        ])
        parts.append(
            '<article class="breakdown-card">'
            f'<div class="breakdown-head"><strong>{e(point["paper_label"])}</strong><span>{e(point["exam_date"])}</span></div>'
            f'<div class="breakdown-meta">{e(detail)}</div>'
            f'<div class="breakdown-meta">总分 {e(format_number(point["total_score"]))}</div>'
            '</article>'
        )
    parts.append("</div>")
    return "".join(parts)


def render_subject_score_table(subject_key: str, rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return render_empty_state("还没有可展示的卷子记录。")
    if subject_key == "politics":
        parts = ['<table class="score-table"><thead><tr><th>日期</th><th>卷型</th><th>卷子</th><th>分数</th></tr></thead><tbody>']
        for row in rows:
            row_date = row.get("date") or row.get("exam_date") or "-"
            parts.append(
                f"<tr><td>{e(row_date)}</td><td>{e(row['paper_type'])}</td><td>{e(row['paper'])}</td><td>{e(format_number(row['total_score']))}</td></tr>"
            )
        parts.append("</tbody></table>")
        return "".join(parts)
    if subject_key == "math1":
        parts = ['<table class="score-table"><thead><tr><th>日期</th><th>卷型</th><th>卷子</th><th>总分</th><th>选填</th><th>大题</th><th>主要问题</th></tr></thead><tbody>']
        for row in rows:
            row_date = row.get("date") or row.get("exam_date") or "-"
            parts.append(
                f"<tr><td>{e(row_date)}</td><td>{e(row['paper_type'])}</td><td>{e(row['paper'])}</td><td>{e(format_number(row['total_score']))}</td><td>{e(format_optional_number(row.get('score_objective')) or '-')}</td><td>{e(format_optional_number(row.get('score_big')) or '-')}</td><td>{e(row['issues'])}</td></tr>"
            )
        parts.append("</tbody></table>")
        return "".join(parts)
    if subject_key == "408":
        parts = ['<table class="score-table"><thead><tr><th>日期</th><th>卷型</th><th>卷子</th><th>总分</th><th>主要薄弱科</th><th>备注</th></tr></thead><tbody>']
        for row in rows:
            row_date = row.get("date") or row.get("exam_date") or "-"
            main_weakness = row.get("main_weakness") or top_weakness_from_408_record(row) or row.get("issues", "")
            parts.append(
                f"<tr><td>{e(row_date)}</td><td>{e(row['paper_type'])}</td><td>{e(row['paper'])}</td><td>{e(format_number(row['total_score']))}</td><td>{e(main_weakness)}</td><td>{e(row['note'])}</td></tr>"
            )
        parts.append("</tbody></table>")
        return "".join(parts)
    parts = ['<table class="score-table"><thead><tr><th>日期</th><th>卷型</th><th>卷子</th><th>总分</th><th>六项分解</th></tr></thead><tbody>']
    for row in rows:
        row_date = row.get("date") or row.get("exam_date") or "-"
        detail = " / ".join([
            f"完形 {format_optional_number(row.get('score_cloze')) or '-'}",
            f"阅读 {format_optional_number(row.get('score_reading')) or '-'}",
            f"新题型 {format_optional_number(row.get('score_new_type')) or '-'}",
            f"翻译 {format_optional_number(row.get('score_translation')) or '-'}",
            f"小作文 {format_optional_number(row.get('score_short_essay')) or '-'}",
            f"大作文 {format_optional_number(row.get('score_long_essay')) or '-'}",
        ])
        parts.append(
            f"<tr><td>{e(row_date)}</td><td>{e(row['paper_type'])}</td><td>{e(row['paper'])}</td><td>{e(format_number(row['total_score']))}</td><td>{e(detail)}</td></tr>"
        )
    parts.append("</tbody></table>")
    return "".join(parts)


SUBJECT_BY_TAB_ID = {meta["tab_id"]: subject for subject, meta in SUBJECT_META.items()}


def render_subject_filter_panels(subject_key: str, trend_data: Mapping[str, object]) -> str:
    labels = [("all", "全部"), ("真题", "真题"), ("模拟", "模拟")]
    subject = SUBJECT_BY_TAB_ID[subject_key]
    meta = SUBJECT_META[subject]
    color = meta["color"]
    y_min, y_max, y_step = 0.0, meta["total_score"], meta["y_step"]
    button_parts = ['<div class="chip-row">']
    panel_parts = []
    has_loss_metrics = bool(trend_data.get("has_loss_metrics"))
    for index, (filter_key, label) in enumerate(labels):
        target = f"{subject_key}-{filter_key}"
        button_parts.append(
            f'<button type="button" class="chip-button{" active" if index == 0 else ""}" data-chip-group="{subject_key}" data-target="{target}">{e(label)}</button>'
        )
        rows = trend_data["filters"][filter_key]
        chart = render_line_chart(rows, color, "当前筛选下还没有成绩记录。", y_min, y_max, y_step)
        if subject_key == "math1":
            breakdown = render_math_breakdown_rows(rows)
        elif subject_key == "408":
            score_view = render_408_metric_rows(rows, "score")
            if has_loss_metrics:
                loss_view = render_408_metric_rows(rows, "loss")
                breakdown = (
                    f'<div class="chip-row compact">'
                    f'<button type="button" class="chip-button active" data-chip-group="{target}-metric" data-target="{target}-score">实际得分</button>'
                    f'<button type="button" class="chip-button" data-chip-group="{target}-metric" data-target="{target}-loss">失分/错题数</button>'
                    f'</div>'
                    f'<div id="{target}-score" class="metric-subpanel active">{score_view}</div>'
                    f'<div id="{target}-loss" class="metric-subpanel">{loss_view}</div>'
                )
            else:
                breakdown = score_view
        else:
            breakdown = render_english_breakdown_rows(rows)
        panel_parts.append(
            f'<div id="{target}" class="subject-filter-panel{" active" if index == 0 else ""}">'
            f'<div class="mini-panel"><h3>总分趋势</h3>{chart}</div>'
            f'<div class="mini-panel"><h3>板块分解</h3>{breakdown}</div>'
            f'<div class="mini-panel"><h3>最近卷子成绩</h3>{render_subject_score_table(subject_key, sorted(rows, key=lambda item: (item["exam_date"], item["paper_type"], item["paper"]), reverse=True)[:6])}</div>'
            '</div>'
        )
    button_parts.append("</div>")
    return "".join(button_parts) + "".join(panel_parts)


def render_subject_progress(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return render_empty_state("尚无结构化数据")
    parts = ['<div class="subject-list">']
    for row in rows:
        ratio = float(row.get("gap_ratio", 0.0)) * 100
        gap = row.get("gap")
        gap_text = "-" if gap is None else f"{format_number(abs(float(gap)))} 分差距"
        cards = int(row.get("cards", 0))
        marked = int(row.get("knowledge_marked", 0))
        total = int(row.get("knowledge_total", 0))
        score_badges = []
        if cards:
            score_badges.append(f"{cards} 张错题卡")
        if total:
            score_badges.append(f"知识地图 {marked}/{total}")
        if row.get("has_score"):
            score_badges.append("已有成绩记录")
        if row.get("has_chapter_reports"):
            score_badges.append("已有章节报告")
        badges = " · ".join(score_badges) if score_badges else "尚无结构化沉淀"
        parts.append(
            '<article class="subject-card">'
            '<div class="subject-head">'
            f'<h3>{e(row["subject"])}</h3>'
            f'<span class="subject-gap">{e(gap_text)}</span>'
            "</div>"
            '<div class="subject-scoreline">'
            f'<span>当前 {e(format_number(row.get("current")))}</span>'
            f'<span>目标 {e(format_number(row.get("target")))}</span>'
            "</div>"
            '<div class="subject-gap-track">'
            f'<div class="subject-gap-fill" style="width: {ratio:.1f}%"></div>'
            "</div>"
            f'<p class="subject-judge">{e(row.get("judgement", ""))}</p>'
            f'<p class="subject-badges">{e(badges)}</p>'
            "</article>"
        )
    parts.append("</div>")
    return "".join(parts)


def render_heatmap(cells: Sequence[Mapping[str, object]], empty_message: str) -> str:
    if not cells:
        return render_empty_state(empty_message)
    parts = ['<div class="heatmap">']
    for cell in cells:
        parts.append(
            f'<div class="heat-cell level-{int(cell["level"])}" '
            f'title="{e(cell["date"])}: {e(cell["count"])}"></div>'
        )
    parts.append("</div>")
    return "".join(parts)


def render_top_chapters(rows: Sequence[Mapping[str, object]], empty_message: str) -> str:
    if not rows:
        return render_empty_state(empty_message)
    parts = ['<div class="chapter-list">']
    for row in rows:
        parts.append(
            '<article class="chapter-card">'
            f'<div class="chapter-title">{e(row["subject"])} / {e(row["chapter"])}</div>'
            f'<div class="chapter-meta">到期 {int(row["due_cards"])} · 未掌握 {int(row["not_mastered_cards"])} · 累计 {int(row["total_cards"])}</div>'
            "</article>"
        )
    parts.append("</div>")
    return "".join(parts)


def render_knowledge_rows(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return render_empty_state("尚无结构化数据")
    parts = ['<div class="knowledge-list">']
    for row in rows:
        total = int(row.get("total_topics", 0))
        if not total:
            parts.append(
                '<article class="knowledge-card">'
                f'<div class="knowledge-title">{e(row["subject"])}</div>'
                '<div class="knowledge-empty">尚无知识地图数据</div>'
                "</article>"
            )
            continue
        segments = []
        for key, klass in (("会", "seg-mastered"), ("半会", "seg-partial"), ("不会", "seg-weak"), ("unmarked", "seg-unmarked")):
            value = int(row.get(key, 0))
            width = value / total * 100 if total else 0
            label = key if key != "unmarked" else "未标注"
            segments.append(
                f'<div class="km-seg {klass}" style="width: {width:.1f}%" title="{e(label)} {value}"></div>'
            )
        parts.append(
            '<article class="knowledge-card">'
            f'<div class="knowledge-title">{e(row["subject"])}</div>'
            f'<div class="knowledge-subtitle">已标注 {int(row["marked_topics"])}/{total}</div>'
            '<div class="km-track">' + "".join(segments) + "</div>"
            f'<div class="knowledge-legend">会 {int(row["会"])} · 半会 {int(row["半会"])} · 不会 {int(row["不会"])} · 未标注 {int(row["unmarked"])}</div>'
            "</article>"
        )
    parts.append("</div>")
    return "".join(parts)


def render_quality_table(rows: Sequence[Mapping[str, object]]) -> str:
    if not rows:
        return render_empty_state("尚无结构化数据")
    headers = ["日志", "错题", "地图", "已标注", "模考", "复盘", "章节报告"]
    keys = ["logs", "wrong_cards", "knowledge_map", "marked_topics", "mock", "recap", "chapter_report"]
    parts = [
        '<table class="quality-table"><thead><tr><th>科目</th>' +
        "".join(f"<th>{e(header)}</th>" for header in headers) +
        "</tr></thead><tbody>"
    ]
    for row in rows:
        parts.append(f"<tr><td>{e(row['subject'])}</td>")
        for key in keys:
            mark = "●" if row[key] else "○"
            klass = "ok" if row[key] else "missing"
            parts.append(f'<td class="{klass}">{mark}</td>')
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def render_warning_list(items: Sequence[str]) -> str:
    if not items:
        return render_empty_state("当前没有明显的结构化缺口。")
    return "<ul class=\"warning-list\">" + "".join(f"<li>{e(item)}</li>" for item in items) + "</ul>"


def render_focus_list(items: Sequence[str], empty_message: str) -> str:
    if not items:
        return render_empty_state(empty_message)
    return "<ol class=\"focus-list\">" + "".join(f"<li>{e(item)}</li>" for item in items[:5]) + "</ol>"


def render_recent_outputs(recent_outputs: Mapping[str, Mapping[str, int]]) -> str:
    parts = ['<div class="output-grid">']
    for label, payload in (("最近一周", recent_outputs["week"]), ("最近一月", recent_outputs["month"])):
        parts.append(
            '<article class="output-card">'
            f'<h3>{e(label)}</h3>'
            f'<p>日志 {payload["logs"]} · 新卡 {payload["cards"]} · 复盘 {payload["recaps"]} · 模考 {payload["mock_reports"]} · 章节报告 {payload["chapter_reports"]}</p>'
            "</article>"
        )
    parts.append("</div>")
    return "".join(parts)


def render_html(payload: Mapping[str, object]) -> str:
    overview = payload["overview"]
    subjects = payload["subjects"]
    reviews = payload["reviews"]
    score_trends = payload["score_trends"]
    knowledge_maps = payload["knowledge_maps"]
    activity = payload["activity"]
    quality = payload["quality"]
    results = payload["results"]
    archive = payload["archive"]

    days_until_exam = overview["days_until_exam"]
    days_text = "-" if days_until_exam is None else str(days_until_exam)
    recap_status = f'复盘 {overview["reports_status"]["recap_count"]} / 模考 {overview["reports_status"]["mock_count"]}'

    metric_cards = "".join([
        render_metric_card("距考试", days_text, f'考试日 {overview["exam_date"]}', "gold"),
        render_metric_card("最近学习", overview["latest_log_date"], f'连续 {overview["log_streak_days"]} 天', "ink"),
        render_metric_card("14 天活跃", str(overview["active_days_14"]), "最近两周有记录的天数", "mint"),
        render_metric_card("到期复习", str(overview["due_total"]), "今天该先止损多少旧题", "alert"),
        render_metric_card("本周新卡", str(overview["new_cards_this_week"]), "这一周新增的结构化错题", "rose"),
        render_metric_card("报告状态", recap_status, "复盘与模考是否在推进", "slate"),
    ])
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kaoyan Coach 学习驾驶舱</title>
  <style>
    :root {{
      --bg: #f6f0e7;
      --paper: rgba(255, 250, 244, 0.86);
      --ink: #14213d;
      --muted: #5f6b7a;
      --gold: #b7791f;
      --gold-soft: #f2d3a1;
      --alert: #c2410c;
      --alert-soft: #fdba74;
      --mint: #156f62;
      --mint-soft: #99f6e4;
      --rose: #9f1239;
      --rose-soft: #fda4af;
      --slate: #334155;
      --line: rgba(20, 33, 61, 0.1);
      --shadow: 0 24px 80px rgba(20, 33, 61, 0.08);
      --radius: 22px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(242, 211, 161, 0.55), transparent 30%),
        radial-gradient(circle at 80% 10%, rgba(153, 246, 228, 0.35), transparent 25%),
        linear-gradient(180deg, #f8f4ed 0%, #efe5d8 100%);
      font-family: "Hiragino Sans GB", "PingFang SC", "Noto Sans CJK SC", sans-serif;
      line-height: 1.5;
    }}
    .shell {{
      width: min(1240px, calc(100% - 32px));
      margin: 24px auto 60px;
    }}
    .hero {{
      position: relative;
      overflow: hidden;
      background: linear-gradient(135deg, rgba(20, 33, 61, 0.96), rgba(34, 49, 84, 0.92));
      color: #fff6eb;
      border-radius: 32px;
      padding: 32px;
      box-shadow: var(--shadow);
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -40px -60px auto;
      width: 240px;
      height: 240px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(255, 255, 255, 0.18), transparent 70%);
    }}
    .hero h1 {{
      margin: 0 0 10px;
      font-family: Georgia, "Songti SC", "STSong", serif;
      font-size: clamp(32px, 4vw, 48px);
      line-height: 1.02;
      letter-spacing: -0.02em;
    }}
    .hero p {{
      margin: 0;
      max-width: 760px;
      color: rgba(255, 246, 235, 0.8);
      font-size: 16px;
    }}
    .hero-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 18px;
      color: rgba(255, 246, 235, 0.86);
    }}
    .hero-meta span {{
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.08);
      backdrop-filter: blur(12px);
    }}
    .nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 16px 0 0;
    }}
    .nav a, .nav button {{
      border: 0;
      cursor: pointer;
      text-decoration: none;
      color: #fff8ef;
      background: rgba(255, 255, 255, 0.1);
      padding: 10px 14px;
      border-radius: 999px;
      font-size: 14px;
    }}
    .section {{
      margin-top: 22px;
      background: var(--paper);
      border: 1px solid rgba(255, 255, 255, 0.5);
      border-radius: 28px;
      padding: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(20px);
    }}
    .section h2 {{
      margin: 0 0 6px;
      font-family: Georgia, "Songti SC", "STSong", serif;
      font-size: 28px;
      letter-spacing: -0.02em;
    }}
    .section .lede {{
      margin: 0 0 18px;
      color: var(--muted);
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 14px;
    }}
    .metric-card {{
      border-radius: 22px;
      padding: 18px;
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid var(--line);
      min-height: 152px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .metric-title {{
      color: var(--muted);
      font-size: 13px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .metric-value {{
      font-size: clamp(28px, 3vw, 38px);
      font-weight: 700;
      line-height: 1;
      margin: 10px 0 6px;
    }}
    .metric-caption {{
      color: var(--muted);
      font-size: 14px;
    }}
    .tone-gold .metric-value {{ color: var(--gold); }}
    .tone-ink .metric-value {{ color: var(--ink); }}
    .tone-mint .metric-value {{ color: var(--mint); }}
    .tone-alert .metric-value {{ color: var(--alert); }}
    .tone-rose .metric-value {{ color: var(--rose); }}
    .tone-slate .metric-value {{ color: var(--slate); }}
    .split {{
      display: grid;
      grid-template-columns: 1.3fr 0.9fr;
      gap: 18px;
    }}
    .subject-list, .knowledge-list, .output-grid {{
      display: grid;
      gap: 14px;
    }}
    .subject-card, .knowledge-card, .output-card, .chapter-card {{
      border-radius: 20px;
      padding: 18px;
      background: rgba(255, 255, 255, 0.92);
      border: 1px solid var(--line);
    }}
    .subject-head, .subject-scoreline {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: baseline;
    }}
    .subject-head h3, .output-card h3 {{
      margin: 0;
      font-size: 20px;
    }}
    .subject-gap {{
      color: var(--gold);
      font-weight: 700;
    }}
    .subject-scoreline {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 14px;
    }}
    .subject-gap-track, .km-track, .bar-track {{
      position: relative;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(20, 33, 61, 0.08);
    }}
    .subject-gap-track {{
      height: 10px;
      margin-top: 12px;
    }}
    .subject-gap-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--gold), #f0b35c);
    }}
    .subject-judge, .subject-badges, .knowledge-subtitle, .knowledge-legend, .chapter-meta {{
      margin: 10px 0 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .bar-list {{
      display: grid;
      gap: 12px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 110px minmax(0, 1fr) 40px;
      gap: 10px;
      align-items: center;
    }}
    .bar-label, .bar-value {{
      font-size: 14px;
    }}
    .bar-track {{
      height: 12px;
    }}
    .bar-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--ink), #5876b8);
      border-radius: inherit;
    }}
    .panel-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .mini-panel {{
      border-radius: 22px;
      padding: 18px;
      background: rgba(255, 255, 255, 0.92);
      border: 1px solid var(--line);
    }}
    .mini-panel h3 {{
      margin: 0 0 10px;
      font-size: 19px;
    }}
    .trend-chart {{
      width: 100%;
      height: auto;
      display: block;
    }}
    .chart-with-legend {{
      display: grid;
      gap: 12px;
    }}
    .chart-legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .legend-pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(20, 33, 61, 0.06);
      color: var(--muted);
      font-size: 13px;
    }}
    .legend-dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      display: inline-block;
    }}
    .score-table {{
      width: 100%;
      border-collapse: collapse;
      background: rgba(255, 255, 255, 0.92);
      border-radius: 18px;
      overflow: hidden;
    }}
    .score-table th, .score-table td {{
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      font-size: 14px;
      vertical-align: top;
    }}
    .score-table th {{
      color: var(--muted);
      font-weight: 700;
    }}
    .score-summary-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 16px;
    }}
    .subject-tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 16px 0;
    }}
    .tab-button, .chip-button {{
      border: 1px solid rgba(20, 33, 61, 0.12);
      background: rgba(255, 255, 255, 0.9);
      color: var(--ink);
      border-radius: 999px;
      padding: 10px 14px;
      font-size: 14px;
      cursor: pointer;
    }}
    .tab-button.active, .chip-button.active {{
      background: var(--ink);
      color: #fff8ef;
      border-color: var(--ink);
    }}
    .trend-tab-panel, .subject-filter-panel, .metric-subpanel {{
      display: none;
    }}
    .trend-tab-panel.active, .subject-filter-panel.active, .metric-subpanel.active {{
      display: block;
    }}
    .trend-tab-panel {{
      margin-top: 12px;
    }}
    .chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 14px;
    }}
    .chip-row.compact {{
      margin-top: 4px;
    }}
    .breakdown-list {{
      display: grid;
      gap: 10px;
    }}
    .breakdown-card {{
      padding: 14px;
      border-radius: 18px;
      background: rgba(20, 33, 61, 0.04);
      border: 1px solid rgba(20, 33, 61, 0.06);
    }}
    .breakdown-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      font-size: 14px;
      margin-bottom: 10px;
    }}
    .breakdown-meta {{
      color: var(--muted);
      font-size: 14px;
      margin-top: 8px;
    }}
    .stack-track {{
      display: flex;
      height: 12px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(20, 33, 61, 0.08);
    }}
    .stack-seg {{
      height: 100%;
    }}
    .seg-objective {{
      background: #b7791f;
    }}
    .seg-big {{
      background: #1d4ed8;
    }}
    .heatmap {{
      display: grid;
      grid-template-columns: repeat(10, minmax(0, 1fr));
      gap: 6px;
    }}
    .heat-cell {{
      aspect-ratio: 1 / 1;
      border-radius: 8px;
      background: rgba(20, 33, 61, 0.06);
      border: 1px solid rgba(20, 33, 61, 0.03);
    }}
    .level-1 {{ background: rgba(183, 121, 31, 0.28); }}
    .level-2 {{ background: rgba(183, 121, 31, 0.48); }}
    .level-3 {{ background: rgba(183, 121, 31, 0.78); }}
    .chapter-list {{
      display: grid;
      gap: 10px;
    }}
    .chapter-title {{
      font-size: 16px;
      font-weight: 700;
    }}
    .km-track {{
      height: 12px;
      margin-top: 12px;
      display: flex;
    }}
    .km-seg {{ height: 100%; }}
    .seg-mastered {{ background: #0f766e; }}
    .seg-partial {{ background: #eab308; }}
    .seg-weak {{ background: #dc2626; }}
    .seg-unmarked {{ background: rgba(20, 33, 61, 0.12); }}
    .quality-table {{
      width: 100%;
      border-collapse: collapse;
      background: rgba(255, 255, 255, 0.92);
      border-radius: 18px;
      overflow: hidden;
    }}
    .quality-table th, .quality-table td {{
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      text-align: center;
      font-size: 14px;
    }}
    .quality-table th:first-child, .quality-table td:first-child {{
      text-align: left;
      font-weight: 700;
    }}
    .quality-table .ok {{
      color: var(--mint);
      font-weight: 700;
    }}
    .quality-table .missing {{
      color: var(--alert);
      font-weight: 700;
    }}
    .warning-list, .focus-list {{
      margin: 0;
      padding-left: 20px;
      color: var(--ink);
    }}
    .warning-list li + li, .focus-list li + li {{
      margin-top: 8px;
    }}
    .results-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 16px;
    }}
    .result-card {{
      padding: 18px;
      border-radius: 22px;
      background: rgba(255, 255, 255, 0.92);
      border: 1px solid var(--line);
    }}
    .result-card .value {{
      font-size: 34px;
      font-weight: 700;
      margin-top: 8px;
    }}
    .empty-state {{
      border-radius: 18px;
      padding: 16px;
      background: rgba(20, 33, 61, 0.05);
      color: var(--muted);
      font-size: 14px;
    }}
    .payload-drawer {{
      display: none;
      margin-top: 16px;
      border-radius: 20px;
      background: rgba(7, 14, 30, 0.92);
      color: #f8f4ed;
      padding: 18px;
      overflow: auto;
      max-height: 420px;
      font-size: 13px;
    }}
    .tooltip-floating {{
      position: fixed;
      pointer-events: none;
      z-index: 9999;
      max-width: 320px;
      padding: 8px 10px;
      border-radius: 10px;
      background: rgba(20, 33, 61, 0.94);
      color: #fff8ef;
      box-shadow: 0 10px 30px rgba(20, 33, 61, 0.2);
      font-size: 12px;
      line-height: 1.4;
      opacity: 0;
      transform: translateY(4px);
      transition: opacity 120ms ease, transform 120ms ease;
    }}
    .tooltip-floating.visible {{
      opacity: 1;
      transform: translateY(0);
    }}
    .payload-drawer.open {{
      display: block;
    }}
    @media (max-width: 1100px) {{
      .metric-grid, .results-grid {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }}
      .split {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 760px) {{
      .shell {{
        width: min(100% - 20px, 1240px);
        margin-top: 12px;
      }}
      .hero, .section {{
        padding: 18px;
        border-radius: 22px;
      }}
      .metric-grid, .results-grid, .panel-grid {{
        grid-template-columns: 1fr;
      }}
      .bar-row {{
        grid-template-columns: 90px minmax(0, 1fr) 34px;
      }}
      .heatmap {{
        grid-template-columns: repeat(6, minmax(0, 1fr));
      }}
      .quality-table {{
        display: block;
        overflow-x: auto;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <h1>Kaoyan Coach 学习驾驶舱</h1>
      <p>先把真实学习状态摊开，再决定今天该补哪里。这个页面只消费你已经沉淀下来的档案、日志、错题卡、知识地图和报告，不美化空白，也不替你脑补进步。</p>
      <div class="hero-meta">
        <span>生成时间 {e(payload["generated_at"])}</span>
        <span>档案更新 {e(archive["latest_archive_update"])}</span>
        <span>当前阶段 {e(overview["stage"] or "未记录")}</span>
      </div>
      <div class="nav">
        <a href="#overview">总览</a>
        <a href="#subjects">科目进度</a>
        <a href="#score-trends">成绩趋势</a>
        <a href="#reviews">复习止损</a>
        <a href="#quality">沉淀质量</a>
        <a href="#results">成果感</a>
        <button id="toggle-payload" type="button">查看原始数据</button>
      </div>
      <pre id="payload-drawer" class="payload-drawer"></pre>
    </section>

    <section class="section" id="overview">
      <h2>总览卡片</h2>
      <p class="lede">第一屏只回答一件事：你现在的系统状态是在向前推进，还是在悄悄失真。</p>
      <div class="metric-grid">{metric_cards}</div>
    </section>

    <section class="section" id="subjects">
      <h2>科目进度总览</h2>
      <p class="lede">先看分差，再看结构化沉淀是否跟上。当前差距最大的不一定最危险，但长期空白的一定最危险。</p>
      <div class="split">
        <div>
          {render_subject_progress(subjects["progress"])}
        </div>
        <div class="mini-panel">
          <h3>聚焦问题</h3>
          {render_focus_list(archive["focus_problems"], "档案里还没有最近聚焦问题。")}
          <h3 style="margin-top: 18px;">结构化沉淀覆盖</h3>
          <p>{e("、".join(subjects["structured_subjects"]) if subjects["structured_subjects"] else "尚无结构化沉淀")}</p>
          <p style="color: var(--muted);">{e("空白科目：" + "、".join(subjects["blank_subjects"]) if subjects["blank_subjects"] else "当前四科都至少有一层结构化数据。")}</p>
        </div>
      </div>
    </section>

    <section class="section" id="score-trends">
      <h2>成绩趋势面板</h2>
      <p class="lede">一次只看一个维度：总分、单科趋势和模块分数分开读，图表才不会挤成一团。</p>
      <div class="subject-tabs">
        <button type="button" class="tab-button active" data-chip-group="score-tabs" data-target="score-tab-total">总分</button>
        <button type="button" class="tab-button" data-chip-group="score-tabs" data-target="score-tab-math1">数学一</button>
        <button type="button" class="tab-button" data-chip-group="score-tabs" data-target="score-tab-408">408</button>
        <button type="button" class="tab-button" data-chip-group="score-tabs" data-target="score-tab-english1">英语一</button>
        <button type="button" class="tab-button" data-chip-group="score-tabs" data-target="score-tab-politics">政治</button>
      </div>
      <div id="score-tab-total" class="trend-tab-panel active">
        {render_total_score_panel(score_trends)}
      </div>
      <div id="score-tab-math1" class="trend-tab-panel">
        {render_subject_filter_panels("math1", score_trends["math1"])}
      </div>
      <div id="score-tab-408" class="trend-tab-panel">
        {render_subject_filter_panels("408", score_trends["408"])}
      </div>
      <div id="score-tab-english1" class="trend-tab-panel">
        {render_subject_filter_panels("english1", score_trends["english1"])}
      </div>
      <div id="score-tab-politics" class="trend-tab-panel">
        {render_politics_panel(score_trends)}
      </div>
    </section>

    <section class="section" id="reviews">
      <h2>复习止损面板</h2>
      <p class="lede">这里不是展示“我有多少题”，而是暴露“哪一堆旧题再不清就会继续恶化”。</p>
      <div class="panel-grid">
        <div class="mini-panel">
          <h3>到期卡按科目分布</h3>
          {render_bar_rows(reviews["by_subject"], "当前没有到期复习。")}
        </div>
        <div class="mini-panel">
          <h3>到期卡按状态分布</h3>
          {render_bar_rows(reviews["by_status"], "当前没有到期复习。")}
        </div>
        <div class="mini-panel">
          <h3>超期严重度分层</h3>
          {render_bar_rows(reviews["overdue_buckets"], "当前没有到期复习。")}
        </div>
        <div class="mini-panel">
          <h3>最该先清的章节 / 考点</h3>
          {render_top_chapters(reviews["top_chapters"], "尚无错题热点。")}
        </div>
      </div>
    </section>

    <section class="section" id="quality">
      <h2>沉淀质量面板</h2>
      <p class="lede">你的学习系统值不值钱，取决于哪些事实被记下来了，哪些仍然只是聊过但没沉淀。</p>
      <div class="panel-grid">
        <div class="mini-panel">
          <h3>最近 30 天学习日志</h3>
          {render_heatmap(activity["log_heatmap_30"], "还没有学习日志。")}
        </div>
        <div class="mini-panel">
          <h3>最近 30 天错题创建</h3>
          {render_heatmap(activity["card_created_heatmap_30"], "还没有错题创建记录。")}
        </div>
        <div class="mini-panel">
          <h3>最近 30 天错题复习</h3>
          {render_heatmap(activity["card_reviewed_heatmap_30"], "还没有错题复习记录。")}
        </div>
        <div class="mini-panel">
          <h3>知识地图掌握分布</h3>
          {render_knowledge_rows(knowledge_maps["by_subject"])}
        </div>
      </div>
      <div style="margin-top: 16px;">
        <h3 style="margin: 0 0 10px;">数据完整度图</h3>
        {render_quality_table(quality["subject_matrix"])}
      </div>
      <div style="margin-top: 16px;">
        <h3 style="margin: 0 0 10px;">缺失提醒</h3>
        {render_warning_list(quality["warnings"])}
      </div>
    </section>

    <section class="section" id="results">
      <h2>成果感面板</h2>
      <p class="lede">成果感不靠鼓励词，靠能数出来的沉淀：你到底留下了多少可回看的学习资产。</p>
      <div class="results-grid">
        <article class="result-card"><div>已沉淀卡片总数</div><div class="value">{e(results["total_cards"])}</div></article>
        <article class="result-card"><div>推进到半会/会的卡</div><div class="value">{e(results["promoted_cards"])}</div></article>
        <article class="result-card"><div>已覆盖章节数</div><div class="value">{e(results["covered_chapters"])}</div></article>
        <article class="result-card"><div>408 已覆盖模块</div><div class="value">{e(results["covered_modules_408"])}</div></article>
      </div>
      {render_recent_outputs(activity["recent_outputs"])}
      <div style="margin-top: 16px;">
        <h3 style="margin: 0 0 10px;">下一步建议</h3>
        {render_focus_list(archive["next_steps"], "档案里还没有下一步建议。")}
      </div>
    </section>
  </div>

  <script id="payload-json" type="application/json">{payload_json}</script>
  <script>
    const toggle = document.getElementById("toggle-payload");
    const drawer = document.getElementById("payload-drawer");
    const payload = document.getElementById("payload-json").textContent;
    drawer.textContent = payload;
    const tooltip = document.createElement("div");
    tooltip.className = "tooltip-floating";
    document.body.appendChild(tooltip);
    toggle.addEventListener("click", () => {{
      drawer.classList.toggle("open");
    }});
    document.querySelectorAll("[data-chip-group]").forEach((button) => {{
      button.addEventListener("click", () => {{
        const group = button.dataset.chipGroup;
        const target = button.dataset.target;
        document.querySelectorAll(`[data-chip-group="${{group}}"]`).forEach((peer) => peer.classList.remove("active"));
        button.classList.add("active");
        if (!target) return;
        if (group === "score-tabs") {{
          document.querySelectorAll(".trend-tab-panel").forEach((panel) => panel.classList.remove("active"));
        }} else if (group.endsWith("-metric")) {{
          document.querySelectorAll(`#${{CSS.escape(group.replace("-metric", ""))}} .metric-subpanel`).forEach((panel) => panel.classList.remove("active"));
        }} else {{
          document.querySelectorAll(".subject-filter-panel").forEach((panel) => {{
            if (panel.id.startsWith(group + "-")) panel.classList.remove("active");
          }});
        }}
        const targetEl = document.getElementById(target);
        if (targetEl) targetEl.classList.add("active");
      }});
    }});
    const moveTooltip = (event) => {{
      tooltip.style.left = (event.clientX + 14) + "px";
      tooltip.style.top = (event.clientY + 14) + "px";
    }};
    document.querySelectorAll(".tooltip-point").forEach((point) => {{
      point.addEventListener("mouseenter", (event) => {{
        tooltip.textContent = point.dataset.tooltip || "";
        tooltip.classList.add("visible");
        moveTooltip(event);
      }});
      point.addEventListener("mousemove", moveTooltip);
      point.addEventListener("mouseleave", () => {{
        tooltip.classList.remove("visible");
      }});
    }});
  </script>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    today = parse_today(args.today)
    payload = build_payload(obsidian_root, today)

    output_path = resolve_output_path(obsidian_root, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html_content = render_html(payload)
    atomic_write(output_path, html_content)

    result = dict(payload)
    result["path"] = str(output_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
