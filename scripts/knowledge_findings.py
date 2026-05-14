"""知识地图备注栏的结构化卡点（finding）操作。

每条 finding 是四元组：(qid, 暴露日期, 一句话描述, 掌握日期?)，
渲染为表格单元格内 `1. [日期] 描述 (qid-xxx)` 形式，
多条用 `<br>` 分隔；已掌握条目加删除线、显示「暴露日期 → 解决日期」。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Literal, Optional, Tuple

from study_ops import iter_review_cards


FINDING_DESC_MAX_LEN = 40
DEFAULT_MASTERY_THRESHOLD_DAYS = 14
DEFAULT_FOLD_THRESHOLD = 3

QID_PATTERN = r"qid-(?:grill-[0-9a-f]{10}|[0-9a-f]{12})"

FINDING_RE = re.compile(
    r"^(?P<idx>\d+)\.\s+"
    r"(?P<strike_open>~~)?"
    r"\[(?P<start>\d{4}-\d{2}-\d{2})(?:\s*→\s*(?P<end>\d{4}-\d{2}-\d{2}))?\]\s+"
    r"(?P<desc>.+?)\s+"
    rf"\((?P<qid>{QID_PATTERN})\)"
    r"(?P<strike_close>~~)?\s*$"
)

SourceKind = Literal["wrong_card", "grill"]


@dataclass
class Finding:
    qid: str
    first_exposed: date
    description: str
    mastered_at: Optional[date] = None
    source: SourceKind = "wrong_card"
    tombstone: bool = False  # qid 对应的错题卡找不到时设 True


def _truncate_desc(desc: str) -> str:
    desc = desc.strip()
    if len(desc) <= FINDING_DESC_MAX_LEN:
        return desc
    return desc[: FINDING_DESC_MAX_LEN - 1] + "…"


def _infer_source(qid: str) -> SourceKind:
    return "grill" if qid.startswith("qid-grill-") else "wrong_card"


def _parse_one(line: str) -> Optional[Finding]:
    line = line.strip()
    if not line:
        return None
    match = FINDING_RE.match(line)
    if not match:
        return None
    has_open = bool(match.group("strike_open"))
    has_close = bool(match.group("strike_close"))
    if has_open != has_close:
        return None
    strike = has_open
    try:
        start_date = date.fromisoformat(match.group("start"))
    except ValueError:
        return None
    end_raw = match.group("end")
    end_date: Optional[date] = None
    if end_raw:
        try:
            end_date = date.fromisoformat(end_raw)
        except ValueError:
            end_date = None
    if strike and end_date is None:
        return None  # 删除线必须配上解决日期，否则解析失败当 legacy
    if not strike and end_date is not None:
        end_date = None  # 未删除但写了 end，按未掌握处理
    qid = match.group("qid")
    desc = match.group("desc").strip()
    # 描述里可能裹着删除线的内层 ~~，按 strike 判断剥一下
    if strike:
        desc = desc.strip("~ ")
    return Finding(
        qid=qid,
        first_exposed=start_date,
        description=desc,
        mastered_at=end_date if strike else None,
        source=_infer_source(qid),
    )


def parse_findings(note_cell: str) -> Tuple[List[Finding], str]:
    """从表格单元格文本里解析 findings，返回 (findings, legacy_text)。

    `note_cell` 可能含 `<br>` 分隔的多行、`<details>...</details>` 折叠块，
    以及任何不符合 Finding 格式的"自由文本"残留。所有无法 parse 的片段汇入 legacy_text。
    """
    findings: List[Finding] = []
    legacy_lines: List[str] = []

    text = note_cell or ""
    # 去掉 <summary> 块（折叠标题，不是数据）
    text = re.sub(r"<summary\b[^>]*>.*?</summary>", "", text, flags=re.I | re.S)
    # 把 <details> 和 </details> 标签去掉但保留内部内容
    text = re.sub(r"</?details\b[^>]*>", "", text, flags=re.I)
    # 按 <br> 拆分
    pieces = re.split(r"<br\s*/?>", text)

    for raw in pieces:
        piece = raw.strip()
        if not piece:
            continue
        parsed = _parse_one(piece)
        if parsed:
            findings.append(parsed)
        else:
            legacy_lines.append(piece)

    legacy_text = "\n".join(legacy_lines).strip()
    return findings, legacy_text


def merge_findings(
    existing: List[Finding],
    new_qid: str,
    new_date: date,
    new_desc: str,
    source: SourceKind = "wrong_card",
) -> List[Finding]:
    """按 qid 去重合并。

    - qid 已存在 → 更新 description（不动 first_exposed、mastered_at、source）
    - qid 不存在 → 追加新条目，mastered_at=None
    """
    truncated = _truncate_desc(new_desc)
    for finding in existing:
        if finding.qid == new_qid:
            finding.description = truncated
            return existing
    existing.append(
        Finding(
            qid=new_qid,
            first_exposed=new_date,
            description=truncated,
            mastered_at=None,
            source=source,
        )
    )
    return existing


def sync_mastered_status(
    findings: List[Finding],
    obsidian_root: Path,
    threshold_days: int = DEFAULT_MASTERY_THRESHOLD_DAYS,
) -> List[Finding]:
    """根据每条 finding 对应错题卡的 review_interval 自动维护 mastered_at。

    规则：
    - source='grill' 跳过（无真实错题卡可参考）
    - source='wrong_card' 且 review_interval ≥ threshold_days → 设 mastered_at = card.last_review_at
    - 已经划掉的（mastered_at 已设）不再动
    - 卡片找不到 → 设 tombstone=True
    """
    card_index: dict[str, Tuple[int, Optional[date]]] = {}
    for card in iter_review_cards(obsidian_root):
        if card["icloud_placeholder"]:
            continue
        fm = card["frontmatter"]
        qid = str(fm.get("question_id", "")).strip()
        if not qid:
            continue
        interval = card["review_interval"]
        if interval is None:
            continue
        last_review_str = str(fm.get("last_review_at", "")).strip()
        last_review: Optional[date] = None
        if last_review_str:
            try:
                last_review = date.fromisoformat(last_review_str)
            except ValueError:
                last_review = None
        card_index[qid] = (interval, last_review)

    for finding in findings:
        if finding.source == "grill":
            continue
        if finding.mastered_at is not None:
            continue
        if finding.qid not in card_index:
            finding.tombstone = True
            continue
        interval, last_review = card_index[finding.qid]
        if interval >= threshold_days and last_review is not None:
            finding.mastered_at = last_review

    return findings


def _render_one(idx: int, finding: Finding) -> str:
    desc = finding.description
    if finding.mastered_at:
        timestamp = f"[{finding.first_exposed.isoformat()} → {finding.mastered_at.isoformat()}]"
        return f"{idx}. ~~{timestamp} {desc} ({finding.qid})~~"
    timestamp = f"[{finding.first_exposed.isoformat()}]"
    return f"{idx}. {timestamp} {desc} ({finding.qid})"


def render_findings(
    findings: List[Finding],
    fold_threshold: int = DEFAULT_FOLD_THRESHOLD,
) -> str:
    """渲染为表格单元格字符串。空列表返回 ""。

    排序规则：未掌握在前（按 first_exposed），已掌握在后（按 mastered_at）。
    已掌握条目数 ≥ fold_threshold 时包 `<details>` 折叠。
    """
    if not findings:
        return ""

    unmastered: List[Finding] = []
    mastered: List[Finding] = []
    for f in findings:
        if f.mastered_at:
            mastered.append(f)
        else:
            unmastered.append(f)

    unmastered.sort(key=lambda f: (f.first_exposed, f.qid))
    mastered.sort(key=lambda f: (f.mastered_at or date.min, f.first_exposed, f.qid))

    lines: List[str] = []
    idx = 1
    for f in unmastered:
        lines.append(_render_one(idx, f))
        idx += 1

    if mastered:
        if len(mastered) >= fold_threshold:
            inner_lines: List[str] = []
            for f in mastered:
                inner_lines.append(_render_one(idx, f))
                idx += 1
            inner = "<br>".join(inner_lines)
            lines.append(
                f"<details><summary>已掌握 {len(mastered)} 条</summary>{inner}</details>"
            )
        else:
            for f in mastered:
                lines.append(_render_one(idx, f))
                idx += 1

    return "<br>".join(lines)
