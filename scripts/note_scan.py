"""扫描 知识笔记/ 目录，按 frontmatter `created` 聚合笔记。

提供三个层级的能力：
- `auto_fill_created_frontmatter`: 给缺 `created` 字段的笔记按 mtime 推断后回写。
- `scan_notes_in_range` / `scan_all_notes`: 解析路径与 frontmatter，返回 `NoteEntry` 列表。
- `render_*_section`: 渲染学习日志「今日新增笔记」段、复盘「知识沉淀」段。

章节号归一化（`extract_chapter_num`）打通 知识笔记 / 错题本 / 知识地图 三处不同的章节命名，
让上层做跨表交叉对照（only-drilling / only-theory 预警）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from frontmatter import parse_frontmatter, serialize_frontmatter

NOTES_DIR_NAME = "知识笔记"

_ARABIC_CH_RE = re.compile(r"ch(\d+)", re.IGNORECASE)
_LEADING_NUM_RE = re.compile(r"^(\d+)\s*第")
_BOLD_LEADING_NUM_RE = re.compile(r"^(\d{1,3})\s+第")
_CHINESE_CHAPTER_RE = re.compile(r"第([零一二三四五六七八九十百]+)章")
# 兜底：`01 线性表` / `03 树与二叉树` / `01 马克思主义哲学` 这种「N 中文名」形态。
# 限定 1-2 位数字 + 至少一个非连字符字符，避免误伤日期 `2026-05-24` 或年份 `2026`。
_BARE_LEADING_NUM_RE = re.compile(r"^(\d{1,2})\s+[^\-\d\s]")

# 子科目别名：把 知识笔记 里习惯写的简称统一到 知识地图/错题本 用的标准全称，
# 这样跨表对照（笔记 vs 错题 vs 知识地图）才能正确 join。
SUBGROUP_ALIASES: Dict[str, Dict[str, str]] = {
    "数学一": {
        "高数": "高等数学",
        "线代": "线性代数",
        "概率": "概率论与数理统计",
        "概统": "概率论与数理统计",
    },
    "408": {
        "DS": "数据结构",
        "CO": "计算机组成原理",
        "OS": "操作系统",
        "CN": "计算机网络",
    },
}


def normalize_subgroup(subject: str, subgroup: str) -> str:
    """把简称统一成知识地图/错题本里的标准名。未识别则原样返回。"""
    if not subgroup:
        return ""
    return SUBGROUP_ALIASES.get(subject, {}).get(subgroup, subgroup)


_CN_NUM = {
    "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _cn_to_int(text: str) -> Optional[int]:
    """中文数字转 int，支持 一二三...十九 / 二十 / 二十一 / 一百 / 一百零一 这种常见形态。"""
    if not text:
        return None
    if text in _CN_NUM:
        return _CN_NUM[text]
    # 含「百」
    if "百" in text:
        parts = text.split("百", 1)
        hundreds = _CN_NUM.get(parts[0] or "一", 1)
        rest = parts[1].lstrip("零")
        rest_val = _cn_to_int(rest) if rest else 0
        return hundreds * 100 + (rest_val or 0)
    # 含「十」
    if "十" in text:
        parts = text.split("十", 1)
        tens = _CN_NUM.get(parts[0] or "一", 1)
        units = _CN_NUM.get(parts[1], 0) if parts[1] else 0
        return tens * 10 + units
    # 多位数字串：如 "一九" 罕见，按位累加
    total = 0
    for ch in text:
        if ch in _CN_NUM:
            total = total * 10 + _CN_NUM[ch]
        else:
            return None
    return total


def extract_chapter_num(raw: str) -> Optional[int]:
    """从章节字符串提取数字编号，覆盖以下命名：

    - `ch1 函数 极限 连续`（知识笔记常用）
    - `01 第一章 函数、极限、连续` / `03第三章微分中值定理与泰勒公式`（知识地图 / 错题本）
    - `第十二章 多元函数`（中文数字）
    - `01 线性表` / `03 树与二叉树` / `01 马克思主义哲学`（408 / 政治 等无「章」字命名）
    """
    if not raw:
        return None
    text = raw.strip()
    m = _ARABIC_CH_RE.search(text)
    if m:
        return int(m.group(1))
    m = _LEADING_NUM_RE.match(text)
    if m:
        return int(m.group(1))
    m = _CHINESE_CHAPTER_RE.search(text)
    if m:
        val = _cn_to_int(m.group(1))
        if val is not None:
            return val
    m = _BOLD_LEADING_NUM_RE.match(text)
    if m:
        return int(m.group(1))
    m = _BARE_LEADING_NUM_RE.match(text)
    if m:
        return int(m.group(1))
    return None


@dataclass(frozen=True)
class NoteEntry:
    path_rel: str       # 相对 vault 根：知识笔记/数学一/高数/ch1.../Stolz 定理.md
    subject: str        # 数学一
    subgroup: str       # 高数（可能为 ""）
    chapter_raw: str    # ch1 函数 极限 连续
    chapter_num: Optional[int]
    title: str          # Stolz 定理
    created: date


def parse_note_path(path_rel: str) -> Tuple[str, str, str, str]:
    """从相对路径拆出 (subject, subgroup, chapter_raw, title)。

    支持三种深度：
    - 知识笔记/{科目}/{子科目}/{章节}/{标题}.md  → 全字段
    - 知识笔记/{科目}/{章节}/{标题}.md           → subgroup=""
    - 知识笔记/{科目}/{标题}.md                  → subgroup="", chapter_raw=""
    """
    parts = Path(path_rel).parts
    if parts and parts[0] == NOTES_DIR_NAME:
        parts = parts[1:]
    if not parts:
        return "", "", "", ""
    subject = parts[0]
    title = Path(parts[-1]).stem
    middle = parts[1:-1]
    if len(middle) >= 2:
        subgroup = middle[0]
        chapter_raw = middle[1]
    elif len(middle) == 1:
        subgroup = ""
        chapter_raw = middle[0]
    else:
        subgroup = ""
        chapter_raw = ""
    return subject, subgroup, chapter_raw, title


def _parse_created(value: object) -> Optional[date]:
    if not value:
        return None
    text = str(value).strip().strip('"').strip("'")
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _infer_mtime_date(path: Path) -> date:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).date()
    except OSError:
        return date.today()


def auto_fill_created_frontmatter(obsidian_root: Path) -> Dict[str, object]:
    """扫描 知识笔记/，给缺 `created` 字段的 .md 笔记写回 `created: YYYY-MM-DD`。

    - 已有 frontmatter 但无 `created`：在 frontmatter 块里追加该字段
    - 无 frontmatter：包一层 `---\ncreated: YYYY-MM-DD\n---` 头
    - 已有 `created`：跳过

    用 mtime 推断日期。幂等。
    """
    root = Path(obsidian_root) / NOTES_DIR_NAME
    filled: List[str] = []
    if not root.exists():
        return {"filled": 0, "paths": filled}

    for md_path in sorted(root.rglob("*.md")):
        if md_path.name.startswith("."):
            continue
        try:
            text = md_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm, body, key_order = parse_frontmatter(text)
        if "created" in fm and _parse_created(fm["created"]) is not None:
            continue
        created_str = _infer_mtime_date(md_path).isoformat()
        if fm or key_order:
            fm["created"] = created_str
            if "created" not in key_order:
                key_order.append("created")
            new_text = serialize_frontmatter(fm, key_order, body)
        else:
            # 裸 markdown：包一层 frontmatter
            new_text = f"---\ncreated: {created_str}\n---\n{text}"
        try:
            md_path.write_text(new_text, encoding="utf-8")
            filled.append(str(md_path.relative_to(obsidian_root)))
        except OSError:
            continue
    return {"filled": len(filled), "paths": filled}


def _build_entry(obsidian_root: Path, md_path: Path) -> Optional[NoteEntry]:
    try:
        text = md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    fm, _, _ = parse_frontmatter(text)
    created = _parse_created(fm.get("created"))
    if created is None:
        return None
    try:
        rel = md_path.relative_to(obsidian_root)
    except ValueError:
        return None
    path_rel = str(rel)
    subject, subgroup, chapter_raw, title = parse_note_path(path_rel)
    return NoteEntry(
        path_rel=path_rel,
        subject=subject,
        subgroup=subgroup,
        chapter_raw=chapter_raw,
        chapter_num=extract_chapter_num(chapter_raw),
        title=title,
        created=created,
    )


def scan_all_notes(obsidian_root: Path) -> List[NoteEntry]:
    """扫所有 知识笔记/ 下含有效 `created` 字段的笔记。缺 created 的静默跳过。"""
    root = Path(obsidian_root) / NOTES_DIR_NAME
    if not root.exists():
        return []
    entries: List[NoteEntry] = []
    for md_path in sorted(root.rglob("*.md")):
        if md_path.name.startswith("."):
            continue
        entry = _build_entry(Path(obsidian_root), md_path)
        if entry is not None:
            entries.append(entry)
    return entries


def scan_notes_in_range(obsidian_root: Path, start: date, end: date) -> List[NoteEntry]:
    """按 created 字段过滤指定日期范围内的笔记。"""
    return [n for n in scan_all_notes(obsidian_root) if start <= n.created <= end]


def count_missing_created(obsidian_root: Path) -> int:
    """统计仍然缺 `created` 的笔记数（auto_fill 之后理论上应为 0）。"""
    root = Path(obsidian_root) / NOTES_DIR_NAME
    if not root.exists():
        return 0
    missing = 0
    for md_path in root.rglob("*.md"):
        if md_path.name.startswith("."):
            continue
        try:
            text = md_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm, _, _ = parse_frontmatter(text)
        if _parse_created(fm.get("created")) is None:
            missing += 1
    return missing


def _chapter_label(entry: NoteEntry) -> str:
    """章节展示标签：把 `ch1 函数 极限 连续` 渲染成 `第1章 函数 极限 连续`。"""
    if entry.chapter_num is not None and entry.chapter_raw:
        cleaned = _ARABIC_CH_RE.sub("", entry.chapter_raw, count=1).strip()
        cleaned = re.sub(r"^第[零一二三四五六七八九十百]+章\s*", "", cleaned).strip()
        cleaned = re.sub(r"^\d{1,3}\s*第[零一二三四五六七八九十百]+章\s*", "", cleaned).strip()
        # 兜底：开头还残留 `01 ` 这种数字前缀也去掉
        cleaned = re.sub(r"^\d{1,3}\s+", "", cleaned).strip()
        if cleaned:
            return f"第{entry.chapter_num}章 {cleaned}"
        return f"第{entry.chapter_num}章"
    if entry.chapter_raw:
        return entry.chapter_raw
    return "未分章节"


def _group_for_display(entries: Iterable[NoteEntry]) -> List[Tuple[str, List[NoteEntry]]]:
    groups: Dict[str, List[NoteEntry]] = {}
    order: List[str] = []
    for entry in entries:
        parts = [entry.subject]
        if entry.subgroup:
            parts.append(entry.subgroup)
        parts.append(_chapter_label(entry))
        key = "·".join(parts)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(entry)
    return [(key, groups[key]) for key in order]


def _wikilink(entry: NoteEntry) -> str:
    target = entry.path_rel
    if target.endswith(".md"):
        target = target[:-3]
    return f"[[{target}|{entry.title}]]"


def render_today_notes_section(
    entries: List[NoteEntry],
    missing_created: int,
) -> str:
    """渲染学习日志的「今日新增笔记」区块。"""
    lines = ["## 今日新增笔记"]
    if not entries:
        if missing_created > 0:
            lines.append(
                f"- 今天没有新增笔记。仍有 {missing_created} 篇笔记缺 `created` 字段，"
                f"下次跑脚本时会自动补；如需手动指定日期，可在 frontmatter 里写 `created: YYYY-MM-DD`。"
            )
        else:
            lines.append("- 今天没有新增笔记。")
        return "\n".join(lines)

    for group_key, items in _group_for_display(entries):
        lines.append(f"- **{group_key}**")
        for entry in items:
            lines.append(f"  - {_wikilink(entry)}")
    suffix = f"- 今日合计 {len(entries)} 篇"
    if missing_created > 0:
        suffix += f"（仍有 {missing_created} 篇缺 created，已忽略）"
    suffix += "。"
    lines.append(suffix)
    return "\n".join(lines)


def render_recap_notes_block(entries: List[NoteEntry], period_name: str) -> str:
    """复盘「知识沉淀」段：本周/月新增笔记总数、科目分布、Top 章节。"""
    if not entries:
        return f"- 本{period_name}没有新增笔记；记得粘完新笔记后让脚本扫描一遍。"

    lines = [f"- 本{period_name}共新增 {len(entries)} 篇笔记。"]

    subject_counts: Dict[str, int] = {}
    for entry in entries:
        subject_counts[entry.subject] = subject_counts.get(entry.subject, 0) + 1
    subject_summary = "、".join(
        f"{subject} {count} 篇"
        for subject, count in sorted(subject_counts.items(), key=lambda x: x[1], reverse=True)
    )
    if subject_summary:
        lines.append(f"- 科目分布：{subject_summary}。")

    chapter_counts: Dict[str, int] = {}
    for entry in entries:
        if not entry.chapter_raw:
            continue
        parts = [entry.subject]
        if entry.subgroup:
            parts.append(entry.subgroup)
        parts.append(_chapter_label(entry))
        key = "·".join(parts)
        chapter_counts[key] = chapter_counts.get(key, 0) + 1
    top = sorted(chapter_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    if top:
        top_text = "；".join(f"{key}（{count}）" for key, count in top)
        lines.append(f"- 高产章节：{top_text}。")

    return "\n".join(lines)


def entry_chapter_key(entry: NoteEntry) -> Optional[Tuple[str, str, int]]:
    """生成跨表对照用的三元键 (subject, normalized_subgroup, chapter_num)。

    chapter_num 缺失时返回 None；subgroup 没有时第二位是空串。
    `normalized_subgroup` 经过 `SUBGROUP_ALIASES` 映射，确保和 知识地图/错题本 的命名能 join 上。
    """
    if entry.chapter_num is None:
        return None
    return (entry.subject, normalize_subgroup(entry.subject, entry.subgroup), entry.chapter_num)


__all__ = [
    "NoteEntry",
    "SUBGROUP_ALIASES",
    "extract_chapter_num",
    "normalize_subgroup",
    "parse_note_path",
    "auto_fill_created_frontmatter",
    "count_missing_created",
    "scan_all_notes",
    "scan_notes_in_range",
    "render_today_notes_section",
    "render_recap_notes_block",
    "entry_chapter_key",
]
