"""解析 知识地图/{科目}.md，抽取「子科目 → 章节列表」。

格式（数学一 / 408 / 英语一通用）：

    ## 高等数学
    | 考点 | 掌握度 | ... |
    |------|--------|-----|
    | **01 第一章 函数、极限、连续** | | |
    |   01.1 函数 | | |
    | **02 第二章 导数与微分** | | |

每个 `## <subgroup>` 下面，加粗的章节行用 `**NN 章名**` 形式；NN 是两位数。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

CHAPTER_ROW_RE = re.compile(r"\|\s*\*\*\s*(\d{1,3})\s+(.+?)\s*\*\*\s*\|")
SUBGROUP_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)


@dataclass(frozen=True)
class ChapterEntry:
    subgroup: str       # 高等数学 / 数据结构 / ...
    chapter_num: int    # 1..N
    chapter_name: str   # 第一章 函数、极限、连续 / 线性表


def _strip_section_size_suffix(text: str) -> str:
    """去掉子科目标题里 `(约 56%)` 之类的容量备注。"""
    return re.sub(r"\s*[（(].*?[)）]\s*$", "", text).strip()


def parse_knowledge_map(path: Path) -> List[ChapterEntry]:
    """从单个知识地图文件解析所有章节条目。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    entries: List[ChapterEntry] = []
    current_subgroup = ""
    for line in text.splitlines():
        heading = SUBGROUP_HEADING_RE.match(line)
        if heading:
            current_subgroup = _strip_section_size_suffix(heading.group(1))
            continue
        m = CHAPTER_ROW_RE.search(line)
        if not m:
            continue
        chapter_num = int(m.group(1))
        chapter_name = m.group(2).strip()
        entries.append(
            ChapterEntry(
                subgroup=current_subgroup,
                chapter_num=chapter_num,
                chapter_name=chapter_name,
            )
        )
    return entries


def load_all_maps(obsidian_root: Path) -> Dict[str, List[ChapterEntry]]:
    """读取 知识地图/*.md，返回 {科目: [ChapterEntry...]}。"""
    root = Path(obsidian_root) / "知识地图"
    if not root.exists():
        return {}
    result: Dict[str, List[ChapterEntry]] = {}
    for md_path in sorted(root.glob("*.md")):
        subject = md_path.stem
        entries = parse_knowledge_map(md_path)
        if entries:
            result[subject] = entries
    return result


def total_chapters(entries: List[ChapterEntry]) -> int:
    return len(entries)


def chapters_index(entries: List[ChapterEntry]) -> Dict[int, ChapterEntry]:
    """以 chapter_num 为键的索引。同号取首个。"""
    out: Dict[int, ChapterEntry] = {}
    for entry in entries:
        out.setdefault(entry.chapter_num, entry)
    return out


__all__ = [
    "ChapterEntry",
    "parse_knowledge_map",
    "load_all_maps",
    "total_chapters",
    "chapters_index",
]
