"""结构化日志条目（LogBullet）解析与聚合。

为了让周/月复盘从"数据搬运"升级到"数据洞察"，每条 bullet 在日志里写成：

    - 类型::内容 (科目·子科目·chN) 附加::值

例：
    - 教材::李林高数 p48 → p50 (数学一·高数·ch2)
    - 学习::分段函数可导性的 4 种讨论模板 (数学一·高数·ch2) 信心:中高
    - 卡点::反函数二阶求导识别 (数学一·高数·ch2) → 下次见 D 卷再验证
    - 总结::中值定理三个变体的判断流程 (数学一·高数·ch3)

类型保留集：教材 / 学习 / 卡点 / 总结 / 试错。其它/无前缀的视为"未分类"。
章节标签可省略；省略时该 bullet 不参与按章聚合，只按日期堆叠。

本模块只做解析与聚合，不负责写入日志（写入仍走 log_progress.py 的 bullet_list）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

from note_scan import extract_chapter_num, normalize_subgroup

KNOWN_KINDS = ("教材", "学习", "卡点", "总结", "试错")

# 兜底文案集合：log_progress.py 在用户没传字段时会写这些"空状态提示"。
# 复盘时遇到这些 bullet 一律视为空数据，不能当真实条目抓回来。
PLACEHOLDER_BULLETS = {
    "今天的收获还比较散，建议明天补成更具体的知识点。",
    "今天没有显式记录卡点。",
    "暂无明确记录",
    "暂未指定复习点，建议先回看今天最容易再次出错的内容。",
    "今天没有单独记录训练成绩。",
}

# 教练评语的默认句也屏蔽，避免被当成 highlight 抓回来。
PLACEHOLDER_BULLETS_PREFIX = (
    "今天有沉淀，明天继续围绕最卡的那 1 个点做收口",
)


def is_placeholder_bullet(text: str) -> bool:
    text = text.strip()
    if text in PLACEHOLDER_BULLETS:
        return True
    return any(text.startswith(p) for p in PLACEHOLDER_BULLETS_PREFIX)


_BULLET_KIND_RE = re.compile(r"^(教材|学习|卡点|总结|试错)\s*[:：]{1,2}\s*(.*)$")
# 章节标签：(科目·子科目·chN) 或 (科目·chN) 或 (科目·子科目)
_CHAPTER_TAG_RE = re.compile(r"[（(]\s*([^）)]+?)\s*[）)]")


@dataclass(frozen=True)
class LogBullet:
    day: date
    raw: str            # 原始文本（去掉前缀 `- ` 后）
    kind: str           # 教材/学习/卡点/总结/试错/未分类
    content: str        # 类型::之后的内容（已剥离章节标签）
    subject: str        # 数学一 / 408 / 英语一 / 政治；解不出来则 ""
    subgroup: str       # 高数 / DS / ...；可空
    subgroup_canonical: str  # subgroup 经 normalize_subgroup 映射后的全称
    chapter_num: Optional[int]
    chapter_raw: str    # ch2 / 03第三章 ... 等原文，可空
    extras: str         # 章节标签之外的尾部信息（如 "信心:中高"、"→ 下次..."）

    @property
    def chapter_key(self) -> Optional[Tuple[str, str, int]]:
        if not self.subject or self.chapter_num is None:
            return None
        return (self.subject, self.subgroup_canonical, self.chapter_num)


def _parse_chapter_tag(tag_text: str) -> Tuple[str, str, Optional[int], str]:
    """解析 `数学一·高数·ch2` 这种章节标签，返回 (subject, subgroup, chapter_num, chapter_raw)。"""
    parts = [p.strip() for p in re.split(r"[·•・/]", tag_text) if p.strip()]
    if not parts:
        return "", "", None, ""
    subject = parts[0]
    subgroup = ""
    chapter_raw = ""
    chapter_num: Optional[int] = None
    for part in parts[1:]:
        if extract_chapter_num(part) is not None:
            chapter_raw = part
            chapter_num = extract_chapter_num(part)
        elif not subgroup:
            subgroup = part
    return subject, subgroup, chapter_num, chapter_raw


def parse_log_bullet(raw_text: str, day: date) -> LogBullet:
    """把一行 bullet 解析成 LogBullet。raw_text 已去掉 `- ` 前缀。"""
    text = raw_text.strip()

    # 类型前缀
    m = _BULLET_KIND_RE.match(text)
    if m:
        kind = m.group(1)
        rest = m.group(2).strip()
    else:
        kind = "未分类"
        rest = text

    # 章节标签：取最后一个 (..·..·chN) 形态的括号
    subject = subgroup = chapter_raw = ""
    chapter_num = None
    chapter_match = None
    for cand in _CHAPTER_TAG_RE.finditer(rest):
        inner = cand.group(1)
        if "·" not in inner and "•" not in inner and "・" not in inner and "/" not in inner:
            continue
        s, sg, cn, cr = _parse_chapter_tag(inner)
        if not s:
            continue
        # 只接受识别出科目的标签
        subject, subgroup, chapter_num, chapter_raw = s, sg, cn, cr
        chapter_match = cand

    extras = ""
    content = rest
    if chapter_match is not None:
        content = rest[:chapter_match.start()].rstrip(" ，,")
        extras = rest[chapter_match.end():].strip()

    return LogBullet(
        day=day,
        raw=raw_text,
        kind=kind,
        content=content.strip(),
        subject=subject,
        subgroup=subgroup,
        subgroup_canonical=normalize_subgroup(subject, subgroup),
        chapter_num=chapter_num,
        chapter_raw=chapter_raw,
        extras=extras,
    )


def extract_log_bullets(text: str, heading: str, day: date) -> List[LogBullet]:
    """从单天日志的某个 `## heading` 区块里抽出结构化条目列表。

    自动过滤兜底占位符。
    """
    pattern = rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)"
    match = re.search(pattern, text, re.M | re.S)
    if not match:
        return []
    bullets: List[LogBullet] = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        body = stripped[2:].strip()
        if not body or is_placeholder_bullet(body):
            continue
        bullets.append(parse_log_bullet(body, day))
    return bullets


# ---------------------------------------------------------------------------
# 渲染辅助
# ---------------------------------------------------------------------------


def _format_date_prefix(day: date) -> str:
    return f"[{day.month:02d}-{day.day:02d}]"


def render_bullet_with_date(bullet: LogBullet, show_kind: bool = True) -> str:
    """周/月复盘里展示单条 bullet：`[MM-DD] 学习: 内容 (数学一·高数·第2章)`。"""
    pieces = [_format_date_prefix(bullet.day)]
    if show_kind and bullet.kind != "未分类":
        pieces.append(f"{bullet.kind}:")
    content = bullet.content or bullet.raw
    content = re.sub(r"^(今天|今日|本周|这周)\s*([：:，, ]\s*)?", "", content.strip())
    pieces.append(content)
    tail = ""
    if bullet.subject:
        tag_parts = [bullet.subject]
        if bullet.subgroup_canonical or bullet.subgroup:
            tag_parts.append(bullet.subgroup_canonical or bullet.subgroup)
        if bullet.chapter_num is not None:
            tag_parts.append(f"第{bullet.chapter_num}章")
        tail = " (" + "·".join(tag_parts) + ")"
    extras = (" " + bullet.extras) if bullet.extras else ""
    return " ".join(pieces) + tail + extras


def group_by_chapter(
    bullets: List[LogBullet],
) -> Dict[Tuple[str, str, int], List[LogBullet]]:
    """按 (subject, normalized_subgroup, chapter_num) 聚类；无 chapter_num 的丢入空 key。"""
    groups: Dict[Tuple[str, str, int], List[LogBullet]] = {}
    for b in bullets:
        key = b.chapter_key
        if key is None:
            continue
        groups.setdefault(key, []).append(b)
    return groups


def unbucketed_bullets(bullets: List[LogBullet]) -> List[LogBullet]:
    return [b for b in bullets if b.chapter_key is None]


# ---------------------------------------------------------------------------
# 教材进度聚合
# ---------------------------------------------------------------------------

# 匹配「教材名 pXX → pYY」「教材名 pXX-pYY」（明确的区间表达）
_PROGRESS_RANGE_RE = re.compile(
    r"(?P<book>[^p\n（）()，,。；;]{2,40}?)\s*p(?P<from>\d+)\s*(?:→|->|—|至|到|\-)\s*p(?P<to>\d+)",
    re.IGNORECASE,
)
# 单页表述「教材名 推进到 pXX」「教材名 刷到 pXX」「教材名 看到 pXX」
_PROGRESS_SINGLE_RE = re.compile(
    r"(?P<book>[^（）()，,。；;\n]{2,40}?)\s*(?:推进到|刷到|看到|读到|做到)\s*p(?P<page>\d+)",
)
# 兜底：bullet kind == 教材 时，直接「教材名 pXX」也接受
_PROGRESS_BARE_RE = re.compile(
    r"^(?P<book>[^（）()，,。；;\n]{2,40}?)\s+p(?P<page>\d+)\s*$",
)


@dataclass
class TextbookProgress:
    name: str
    earliest_page: int
    latest_page: int
    earliest_day: date
    latest_day: date
    samples: int


def collect_textbook_progress(bullets: List[LogBullet]) -> List[TextbookProgress]:
    """从 学习/教材 类 bullet 里聚合教材进度区间。

    严格匹配以下表述，避免把"尤其是 pXX"这种句尾页号误识别为进度：
    - "李林高数 p48 → p56"（区间）
    - "李林高数 推进到 p56" / "刷到 p56" / "看到 p56" / "读到 p56" / "做到 p56"
    - 当 bullet 类型显式为 `教材::` 时，额外接受 "李林高数 p56" 这种裸形态
    """
    aggregate: Dict[str, Dict[str, object]] = {}

    def _clean_book(name: str) -> str:
        name = name.strip().rstrip("：:")
        # 去掉教材名末尾的 "ch2" / "第N章" 这种章节后缀
        name = re.sub(r"\s*ch\d+.*$", "", name, flags=re.IGNORECASE).strip()
        name = re.sub(r"\s*第[零一二三四五六七八九十百\d]+章.*$", "", name).strip()
        return name

    def _update(book: str, page: int, day: date) -> None:
        book = _clean_book(book)
        if not book or page <= 0:
            return
        slot = aggregate.setdefault(book, {
            "earliest_page": page,
            "latest_page": page,
            "earliest_day": day,
            "latest_day": day,
            "samples": 0,
        })
        if page < slot["earliest_page"]:
            slot["earliest_page"] = page
            slot["earliest_day"] = day
        if page > slot["latest_page"]:
            slot["latest_page"] = page
            slot["latest_day"] = day
        slot["samples"] = int(slot["samples"]) + 1

    for b in bullets:
        text = (b.content or b.raw).strip()

        # 优先 range 形态
        m_range = _PROGRESS_RANGE_RE.search(text)
        if m_range:
            book = m_range.group("book")
            _update(book, int(m_range.group("from")), b.day)
            _update(book, int(m_range.group("to")), b.day)
            continue

        # 单页明确表达
        m_single = _PROGRESS_SINGLE_RE.search(text)
        if m_single:
            _update(m_single.group("book"), int(m_single.group("page")), b.day)
            continue

        # 教材类型才接受 bare 形态
        if b.kind == "教材":
            m_bare = _PROGRESS_BARE_RE.match(text)
            if m_bare:
                _update(m_bare.group("book"), int(m_bare.group("page")), b.day)

    out: List[TextbookProgress] = []
    for name, slot in aggregate.items():
        out.append(TextbookProgress(
            name=name,
            earliest_page=int(slot["earliest_page"]),
            latest_page=int(slot["latest_page"]),
            earliest_day=slot["earliest_day"],
            latest_day=slot["latest_day"],
            samples=int(slot["samples"]),
        ))
    out.sort(key=lambda x: (x.latest_day, x.latest_page), reverse=True)
    return out


__all__ = [
    "LogBullet",
    "PLACEHOLDER_BULLETS",
    "KNOWN_KINDS",
    "TextbookProgress",
    "collect_textbook_progress",
    "extract_log_bullets",
    "group_by_chapter",
    "is_placeholder_bullet",
    "parse_log_bullet",
    "render_bullet_with_date",
    "unbucketed_bullets",
]
