"""扫描当日活跃的错题卡，提取迁移总结，并渲染为日志区块。

「今日活跃」= 今日新建 + 今日复习且 status ∈ {不会, 半会}。
复习对了的卡（今日历史记录 status=会）不算活跃，整张跳过。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional

from archive_ops import extract_heading_block
from constants import PLAN_SUBJECTS
from study_ops import iter_review_cards


TODAY_WRONG_HEADING = "今日错题归档"
PLACEHOLDER_TOKEN = "待补充"

TAKEAWAY_HEADINGS = {
    "数学一": "下次怎么做",
    "408": "记忆钩子",
}
GENERIC_TAKEAWAY_HEADING = "正确思路 / 核心结论"

HISTORY_LINE_RE = re.compile(
    r"^-\s*(\d{4}-\d{2}-\d{2})\s*-\s*(不会|半会|会)\s*-",
)


@dataclass
class TodayCardInfo:
    path: Path
    relative_path: str
    subject: str
    chapter: str
    topic: str
    status: str
    is_new: bool
    takeaway: str


def _last_history_entry(body: str) -> Optional[tuple]:
    """返回卡片「### 历史记录」最后一行的 (date_str, status)，没有则 None。"""
    block = extract_heading_block(body, "历史记录", level=3)
    if not block:
        return None
    last: Optional[tuple] = None
    for line in block.splitlines():
        stripped = line.strip()
        match = HISTORY_LINE_RE.match(stripped)
        if match:
            last = (match.group(1), match.group(2))
    return last


def _first_bullet(block: str) -> str:
    """从区块里取第一行非占位、非空 bullet。"""
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        if not value or value == PLACEHOLDER_TOKEN:
            continue
        return value
    return ""


def extract_takeaway(body: str, subject: str) -> str:
    """根据科目从卡片正文里提取迁移总结。无法提取时返回空串。"""
    heading = TAKEAWAY_HEADINGS.get(subject, GENERIC_TAKEAWAY_HEADING)
    block = extract_heading_block(body, heading, level=3)
    if not block:
        return ""
    return _first_bullet(block)


def _infer_chapter(card_path: Path, obsidian_root: Path) -> str:
    """从 `错题本/<subject>/.../<最深章节>/<file>.md` 推断章节。

    真实 vault 中目录可能深嵌套（科目/模块/章/节/文件），取卡片直接父目录作为
    章节名，保留最具体的聚类粒度。没有章节目录时返回空串。
    """
    try:
        rel = card_path.relative_to(Path(obsidian_root) / "错题本")
    except ValueError:
        return ""
    if len(rel.parts) <= 2:
        return ""
    return rel.parts[-2]


def scan_today_wrong_cards(obsidian_root: Path, today: date) -> List[TodayCardInfo]:
    """扫描错题本，返回今日活跃卡的列表（按科目顺序 + 章节名稳定排序）。"""
    today_iso = today.isoformat()
    results: List[TodayCardInfo] = []

    for item in iter_review_cards(obsidian_root):
        if item["icloud_placeholder"]:
            continue
        fm = item["frontmatter"]
        first_wrong_at = str(fm.get("first_wrong_at", "")).strip()
        is_new = first_wrong_at == today_iso

        last_entry = _last_history_entry(item["body"])
        today_review_status: Optional[str] = None
        if last_entry and last_entry[0] == today_iso:
            today_review_status = last_entry[1]

        if today_review_status == "会":
            # 今日复习对了，整张跳过——不算暴露面
            continue

        if not is_new and today_review_status not in {"不会", "半会"}:
            continue

        status_value = today_review_status or str(fm.get("status", "")).strip()
        if status_value not in {"不会", "半会"}:
            continue

        chapter = _infer_chapter(item["path"], Path(obsidian_root))
        try:
            relative_path = str(item["path"].relative_to(Path(obsidian_root)))
        except ValueError:
            relative_path = item["path"].name

        results.append(
            TodayCardInfo(
                path=item["path"],
                relative_path=relative_path,
                subject=item["subject"],
                chapter=chapter,
                topic=str(item["topic"]),
                status=status_value,
                is_new=is_new,
                takeaway=extract_takeaway(item["body"], item["subject"]),
            )
        )

    subject_order = {subject: index for index, subject in enumerate(PLAN_SUBJECTS)}
    results.sort(
        key=lambda card: (
            subject_order.get(card.subject, len(subject_order)),
            card.subject,
            card.chapter,
            card.topic,
        )
    )
    return results


def render_today_wrong_section(cards: List[TodayCardInfo]) -> str:
    """渲染完整 markdown 区块。空列表返回 ""，由调用方决定是否插入。"""
    if not cards:
        return ""

    groups: List[tuple] = []
    current_key: Optional[tuple] = None
    current_cards: List[TodayCardInfo] = []
    for card in cards:
        key = (card.subject, card.chapter)
        if key != current_key:
            if current_key is not None:
                groups.append((current_key, current_cards))
            current_key = key
            current_cards = [card]
        else:
            current_cards.append(card)
    if current_key is not None:
        groups.append((current_key, current_cards))

    lines: List[str] = [f"## {TODAY_WRONG_HEADING}"]
    for (subject, chapter), group_cards in groups:
        chapter_label = chapter or "未分类"
        lines.append("")
        lines.append(f"### {subject}·{chapter_label}（{len(group_cards)} 道）")
        for card in group_cards:
            lines.append(f"- [{card.topic}]({card.relative_path}) — {card.status}")
            if card.takeaway:
                lines.append(f"  → 学到：{card.takeaway}")
    return "\n".join(lines)
