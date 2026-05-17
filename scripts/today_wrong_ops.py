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
from constants import PLAN_SUBJECTS, SRS_GRADUATED_INTERVAL_DAYS
from study_ops import iter_review_cards


TODAY_WRONG_HEADING = "今日错题归档"
REVIEW_EFFECTIVENESS_HEADING = "复习效果"
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
    wikilink_target: str   # 相对 vault 根的卡片路径，不含 .md 后缀，用于 Obsidian wikilink
    subject: str
    chapter: str
    topic: str
    status: str
    is_new: bool
    takeaway: str


@dataclass
class ReviewEffectiveness:
    """今日复习的量化效果。

    - `reviewed_today`：今日有复习记录的旧卡数量（不含今日新增卡的初次落库）
    - `mastered_today` / `partial_today` / `failed_today`：今日复习结果分布
    - `new_today`：今日新增的错题卡（first_wrong_at == today）
    - `due_remaining`：今日仍到期但尚未复习的卡数（已"会"则未来不再到期，已复习则 next_review 已推后）
    """

    reviewed_today: int = 0
    mastered_today: int = 0
    partial_today: int = 0
    failed_today: int = 0
    new_today: int = 0
    due_remaining: int = 0

    @property
    def has_activity(self) -> bool:
        return self.reviewed_today > 0 or self.new_today > 0 or self.due_remaining > 0

    @property
    def mastery_rate(self) -> Optional[float]:
        """掌握转化率 = 会 / 今日复习总数；无复习则 None。"""
        if self.reviewed_today == 0:
            return None
        return self.mastered_today / self.reviewed_today

    @property
    def coverage_rate(self) -> Optional[float]:
        """复习覆盖率 = 今日复习数 / (今日复习数 + 仍到期未复习)。"""
        denom = self.reviewed_today + self.due_remaining
        if denom == 0:
            return None
        return self.reviewed_today / denom


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
            rel_to_vault = item["path"].relative_to(Path(obsidian_root))
            wikilink_target = str(rel_to_vault.with_suffix(""))
        except ValueError:
            wikilink_target = item["path"].stem

        results.append(
            TodayCardInfo(
                path=item["path"],
                wikilink_target=wikilink_target,
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
            lines.append(f"- [[{card.wikilink_target}|{card.topic}]] — {card.status}")
            if card.takeaway:
                lines.append(f"  → 学到：{card.takeaway}")
    return "\n".join(lines)


def scan_today_review_stats(obsidian_root: Path, today: date) -> ReviewEffectiveness:
    """统计今日复习活动，用于在学习日志里量化「复习效果」。

    定义：
    - 今日新增（new_today）= first_wrong_at == today 的卡，不计入复习池
    - 今日复习（reviewed_today）= 历史记录最后一行落在今日的旧卡（first_wrong_at != today）
    - 仍到期未复习（due_remaining）= 今日未触碰 + next_review ≤ today + 未毕业
    """
    today_iso = today.isoformat()
    stats = ReviewEffectiveness()

    for item in iter_review_cards(obsidian_root):
        if item["icloud_placeholder"]:
            continue

        fm = item["frontmatter"]
        first_wrong_at = str(fm.get("first_wrong_at", "")).strip()
        is_new = first_wrong_at == today_iso

        last_entry = _last_history_entry(item["body"])
        today_status: Optional[str] = None
        if last_entry and last_entry[0] == today_iso:
            today_status = last_entry[1]

        if is_new:
            stats.new_today += 1
            continue

        if today_status in {"会", "半会", "不会"}:
            stats.reviewed_today += 1
            if today_status == "会":
                stats.mastered_today += 1
            elif today_status == "半会":
                stats.partial_today += 1
            else:
                stats.failed_today += 1
            continue

        next_review = item["next_review"]
        interval = item["review_interval"]
        if next_review is not None and interval is not None:
            if next_review <= today and interval < SRS_GRADUATED_INTERVAL_DAYS:
                stats.due_remaining += 1

    return stats


def render_review_effectiveness_section(stats: ReviewEffectiveness) -> str:
    """渲染「复习效果」区块。无任何今日活动时返回空串。"""
    if not stats.has_activity:
        return ""

    lines = [f"## {REVIEW_EFFECTIVENESS_HEADING}"]

    summary_parts: List[str] = []
    if stats.reviewed_today > 0:
        summary_parts.append(f"今日复习 **{stats.reviewed_today}** 道")
    if stats.new_today > 0:
        summary_parts.append(f"今日新增 **{stats.new_today}** 道")
    if summary_parts:
        lines.append(f"- {' ｜ '.join(summary_parts)}")

    if stats.reviewed_today > 0:
        breakdown = f"会 {stats.mastered_today} / 半会 {stats.partial_today} / 不会 {stats.failed_today}"
        lines.append(f"- **复习结果**：{breakdown}")
        rate = stats.mastery_rate
        if rate is not None:
            lines.append(f"- **掌握转化率**：{rate * 100:.1f}%（会 / 今日复习总数）")

    coverage = stats.coverage_rate
    if coverage is not None and stats.reviewed_today > 0:
        coverage_pct = coverage * 100
        if stats.due_remaining > 0:
            lines.append(f"- **复习覆盖率**：{coverage_pct:.1f}%（仍有 {stats.due_remaining} 道到期未复习）")
        else:
            lines.append(f"- **复习覆盖率**：{coverage_pct:.1f}%（今日到期已全部复习）")
    elif stats.due_remaining > 0:
        lines.append(f"- 当前仍有 **{stats.due_remaining}** 道到期未复习")

    return "\n".join(lines)
