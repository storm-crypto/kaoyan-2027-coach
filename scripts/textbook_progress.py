"""周计划「本周教材进度目标」表格的解析与渲染。"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from archive_ops import extract_heading_block, replace_heading_block


TEXTBOOK_HEADING = "本周教材进度目标"
TEXTBOOK_HEADERS = ("教材", "起点", "终点", "当前", "备注")
TEXTBOOK_SEPARATOR = "|------|------|------|------|------|"
TEXTBOOK_HEADER_ROW = "| 教材 | 起点 | 终点 | 当前 | 备注 |"
TEXTBOOK_HELP_COMMENT = (
    "<!-- 自行填写。脚本不会自动算每日页数，由 /plan_today 读取本表后给出今日任务；"
    "/progress 报告进度时会更新「当前」列。每行格式：教材 | 起点 | 终点 | 当前 | 备注。"
    "「当前」初始可与「起点」相同。-->"
)
PLACEHOLDER_ROW = "| | | | | |"


@dataclass
class TextbookRow:
    name: str
    start: str
    end: str
    current: str
    note: str = ""

    def to_md(self) -> str:
        return f"| {self.name} | {self.start} | {self.end} | {self.current} | {self.note} |"


@dataclass
class TextbookPlanItem:
    row: TextbookRow
    start_page: Optional[int]
    end_page: Optional[int]
    current_page: Optional[int]
    remaining_pages: Optional[int]
    remaining_days: int
    today_pages: Optional[int]
    done: bool
    note: str = ""

    @property
    def name(self) -> str:
        return self.row.name


def parse_page(value: str) -> Optional[int]:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    match = re.search(r"(\d+)", text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _split_row(line: str) -> List[str]:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    return cells


def _is_separator(cells: Sequence[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-+:?", cell) for cell in cells if cell)


def _is_blank(cells: Sequence[str]) -> bool:
    return all(not cell for cell in cells)


def parse_textbook_block(block_text: str) -> List[TextbookRow]:
    rows: List[TextbookRow] = []
    if not block_text:
        return rows
    for raw_line in block_text.splitlines():
        cells = _split_row(raw_line)
        if not cells:
            continue
        if cells[0] in {"教材"}:
            continue
        if _is_separator(cells):
            continue
        if _is_blank(cells):
            continue
        padded = cells + [""] * (5 - len(cells))
        rows.append(
            TextbookRow(
                name=padded[0],
                start=padded[1],
                end=padded[2],
                current=padded[3],
                note=padded[4],
            )
        )
    return rows


def render_textbook_rows(rows: Sequence[TextbookRow]) -> str:
    if not rows:
        return PLACEHOLDER_ROW
    return "\n".join(row.to_md() for row in rows)


def render_textbook_full_block(rows: Sequence[TextbookRow], help_comment: Optional[str] = TEXTBOOK_HELP_COMMENT) -> str:
    """渲染完整的「本周教材进度目标」区块正文（注释 + 空行 + 表头 + 分隔 + 数据行）。"""
    lines: List[str] = []
    if help_comment:
        lines.append(help_comment)
        lines.append("")
    lines.append(TEXTBOOK_HEADER_ROW)
    lines.append(TEXTBOOK_SEPARATOR)
    lines.append(render_textbook_rows(rows))
    return "\n".join(lines)


def week_plan_path(obsidian_root: Path, today: date) -> Path:
    monday = today - timedelta(days=today.weekday())
    iso_year, iso_week_num, _ = monday.isocalendar()
    return Path(obsidian_root) / "周计划" / f"{iso_year}-W{iso_week_num:02d}.md"


def load_week_textbook_rows(obsidian_root: Path, today: date) -> Tuple[Path, List[TextbookRow]]:
    plan_path = week_plan_path(obsidian_root, today)
    if not plan_path.exists():
        return plan_path, []
    text = plan_path.read_text(encoding="utf-8")
    block = extract_heading_block(text, TEXTBOOK_HEADING)
    return plan_path, parse_textbook_block(block)


def build_plan_items(rows: Sequence[TextbookRow], today: date) -> List[TextbookPlanItem]:
    # 「剩余天数」包含今天本身，以便周日仍能计算出当日任务（=剩余页数）。
    days_remaining = max(1, 7 - today.weekday())
    items: List[TextbookPlanItem] = []
    for row in rows:
        start = parse_page(row.start)
        end = parse_page(row.end)
        current = parse_page(row.current) if row.current else start
        remaining_pages: Optional[int] = None
        today_pages: Optional[int] = None
        done = False
        note = ""
        if end is None or current is None:
            note = "页码格式无法解析，跳过自动计算"
        else:
            remaining_pages = max(0, end - current)
            if remaining_pages == 0:
                done = True
            else:
                today_pages = max(1, math.ceil(remaining_pages / days_remaining))
                today_pages = min(today_pages, remaining_pages)
        items.append(
            TextbookPlanItem(
                row=row,
                start_page=start,
                end_page=end,
                current_page=current,
                remaining_pages=remaining_pages,
                remaining_days=days_remaining,
                today_pages=today_pages,
                done=done,
                note=note,
            )
        )
    return items


def render_today_textbook_section(items: Sequence[TextbookPlanItem]) -> str:
    if not items:
        return ""
    lines: List[str] = ["## 教材进度", "| 教材 | 当前 | 终点 | 剩余 | 剩余天 | 今日建议 | 备注 |", "|------|------|------|------|--------|----------|------|"]
    for item in items:
        current = f"p{item.current_page}" if item.current_page is not None else item.row.current or "-"
        end = f"p{item.end_page}" if item.end_page is not None else item.row.end or "-"
        if item.done:
            today_text = "已完成 ✅"
            remaining_text = "0"
        elif item.today_pages is None:
            today_text = "-"
            remaining_text = "-"
        else:
            today_text = f"p{item.current_page + 1} → p{item.current_page + item.today_pages}（{item.today_pages} 页）"
            remaining_text = str(item.remaining_pages)
        days_remaining = str(item.remaining_days)
        merged_note_parts: List[str] = []
        if item.row.note:
            merged_note_parts.append(item.row.note)
        if item.note:
            merged_note_parts.append(item.note)
        note = " / ".join(merged_note_parts)
        lines.append(
            f"| {item.row.name} | {current} | {end} | {remaining_text} | {days_remaining} | {today_text} | {note} |"
        )
    return "\n".join(lines)


def update_current_page(plan_path: Path, textbook_name: str, new_current: str) -> Tuple[bool, str]:
    """更新本周计划文件里指定教材的「当前」列。返回 (success, message)。"""
    if not plan_path.exists():
        return False, f"未找到本周计划文件：{plan_path}"
    text = plan_path.read_text(encoding="utf-8")
    block = extract_heading_block(text, TEXTBOOK_HEADING)
    if not block:
        return False, "本周计划缺少「本周教材进度目标」区块"
    rows = parse_textbook_block(block)
    target_name = textbook_name.strip()
    matched: Optional[TextbookRow] = None
    for row in rows:
        if row.name == target_name:
            matched = row
            break
    if matched is None:
        for row in rows:
            if target_name and target_name in row.name:
                matched = row
                break
    if matched is None:
        return False, f"未在表中找到教材：{textbook_name}（可在周计划文件里先加一行）"
    matched.current = new_current.strip()
    new_block = render_textbook_full_block(rows, _detect_existing_comment(block))
    try:
        new_text = replace_heading_block(text, TEXTBOOK_HEADING, new_block)
    except ValueError as exc:
        return False, f"更新失败：{exc}"
    plan_path.write_text(new_text, encoding="utf-8")
    return True, f"已更新「{matched.name}」当前进度为 {matched.current}"


def _detect_existing_comment(block_text: str) -> str:
    """如果区块里已经有 HTML 注释（用户可能改过），保留原注释；否则用默认。"""
    if not block_text:
        return TEXTBOOK_HELP_COMMENT
    match = re.search(r"<!--.*?-->", block_text, flags=re.S)
    if match:
        return match.group(0)
    return TEXTBOOK_HELP_COMMENT
