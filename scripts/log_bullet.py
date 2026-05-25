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


# 隐式章节推断关键词。当 bullet 没显式 (科目·子科目·chN) 标签时，
# 通过文本里出现的子科目/章节关键词反推。比显式标签弱但能救回大量
# 自然语言写的旧日志。
SUBGROUP_KEYWORD_HINTS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "数学一": {
        # 长 keyword 优先（"李林高数" 比 "高数" 更精确）
        "高等数学": ("李林高数", "高等数学", "高数"),
        "线性代数": ("线性代数", "线代"),
        "概率论与数理统计": ("概率论", "数理统计", "概统"),
    },
    "408": {
        "数据结构": ("王道数据结构", "数据结构"),
        "计算机组成原理": ("计算机组成原理", "组成原理", "计组"),
        "操作系统": ("操作系统",),
        "计算机网络": ("计算机网络", "计网"),
    },
}

CHAPTER_KEYWORD_HINTS: Dict[Tuple[str, str], Dict[int, Tuple[str, ...]]] = {
    ("数学一", "高等数学"): {
        1: ("函数极限", "数列极限", "无穷小", "函数的连续性", "间断点"),
        2: ("导数与微分", "可导性", "可微性", "求导法", "高阶导数", "微分计算", "反函数二阶求导"),
        3: ("中值定理", "拉格朗日中值", "罗尔定理", "柯西中值", "泰勒公式", "泰勒展开", "微分中值"),
        4: ("单调性", "极值与最值", "凹凸性", "拐点", "渐近线", "导数的应用"),
        5: ("不定积分",),
        6: ("定积分", "反常积分", "积分上限函数"),
        8: ("多元函数微分", "偏导数", "全微分", "隐函数微分", "复合函数偏导"),
        9: ("微分方程",),
        10: ("二重积分",),
        11: ("空间解析", "向量代数", "平面方程", "曲面方程"),
        12: ("无穷级数", "常数项级数", "幂级数", "傅里叶级数"),
        13: ("三重积分", "第一型曲线", "第一型曲面"),
        14: ("第二型曲线", "第二型曲面"),
    },
    ("数学一", "线性代数"): {
        1: ("行列式", "克拉默"),
        2: ("矩阵", "逆矩阵", "矩阵的秩", "初等变换", "初等矩阵"),
        3: ("向量组", "线性相关", "向量空间"),
        4: ("线性方程组", "齐次方程", "非齐次方程"),
        5: ("特征值", "特征向量", "相似矩阵", "对角化"),
        6: ("二次型", "正定"),
    },
    ("数学一", "概率论与数理统计"): {
        1: ("随机事件", "概率公式", "全概率", "贝叶斯", "事件独立性"),
        2: ("一维随机变量", "离散型随机", "连续型随机", "分布函数", "概率密度"),
        3: ("联合分布", "边缘分布", "二维随机变量"),
        4: ("数学期望", "期望与方差", "协方差", "相关系数"),
        5: ("大数定律", "中心极限"),
        6: ("抽样分布",),
        7: ("点估计", "区间估计"),
        8: ("假设检验",),
    },
    ("408", "数据结构"): {
        1: ("线性表", "顺序表", "链表"),
        2: ("栈", "队列", "数组的存储"),
        3: ("二叉树", "线索二叉树", "哈夫曼", "B 树", "B+ 树"),
        4: ("图的存储", "图的遍历", "最小生成树", "最短路径", "拓扑排序"),
        5: ("查找", "折半", "散列表"),
        6: ("排序", "插入排序", "交换排序", "选择排序", "归并排序"),
    },
}

# 内嵌 chN（要求前后不是字母数字，避免误匹配 "much2" 这类）
_INLINE_CHN_RE = re.compile(r"(?:^|[^a-zA-Z0-9])ch(\d{1,2})(?:[^a-zA-Z0-9]|$)", re.IGNORECASE)
# 「第N章」中文或数字
_INLINE_CHAPTER_ZH_RE = re.compile(r"第([零一二三四五六七八九十百\d]{1,4})章")
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn_digits_to_int(text: str) -> Optional[int]:
    """中文数字 → int，支持「一二三...十九 / 二十 / 二十一 / 一百零五」等常见形态。"""
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in _CN_DIGITS:
        return _CN_DIGITS[text]
    if "百" in text:
        head, tail = text.split("百", 1)
        hundreds = _CN_DIGITS.get(head or "一", 1)
        rest = tail.lstrip("零")
        rest_val = _cn_digits_to_int(rest) if rest else 0
        return hundreds * 100 + (rest_val or 0)
    if "十" in text:
        head, tail = text.split("十", 1)
        tens = _CN_DIGITS.get(head or "一", 1)
        units = _CN_DIGITS.get(tail, 0) if tail else 0
        return tens * 10 + units
    return None


def _infer_subject_subgroup(text: str) -> Tuple[str, str]:
    """根据文本里的子科目关键词推断 (subject, subgroup_canonical)。

    匹配最长关键词优先（"李林高数" 比 "高数" 优先），避免短词误伤。
    没匹配上则返回 ("", "")。
    """
    if not text:
        return "", ""
    candidates: List[Tuple[int, str, str, str]] = []
    for subject, subgroups in SUBGROUP_KEYWORD_HINTS.items():
        for subgroup_canonical, keywords in subgroups.items():
            for kw in keywords:
                if kw:
                    candidates.append((len(kw), subject, subgroup_canonical, kw))
    candidates.sort(reverse=True)
    for _, subject, subgroup_canonical, kw in candidates:
        if kw in text:
            return subject, subgroup_canonical
    return "", ""


def _infer_chapter_num(text: str, subject: str, subgroup_canonical: str) -> Optional[int]:
    """根据 bullet 正文内出现的章节线索推断 chapter_num。

    优先级：内嵌 chN > 第N章 > (subject, subgroup) 关键词最高分。
    """
    if not text:
        return None
    m = _INLINE_CHN_RE.search(text)
    if m:
        return int(m.group(1))
    m = _INLINE_CHAPTER_ZH_RE.search(text)
    if m:
        val = _cn_digits_to_int(m.group(1))
        if val is not None:
            return val
    if subject and subgroup_canonical:
        hints = CHAPTER_KEYWORD_HINTS.get((subject, subgroup_canonical))
        if hints:
            best_chapter: Optional[int] = None
            best_score = 0
            for chapter_num, keywords in hints.items():
                score = sum(1 for kw in keywords if kw in text)
                if score > best_score:
                    best_score = score
                    best_chapter = chapter_num
            if best_chapter is not None and best_score >= 1:
                return best_chapter
    return None


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

    # 隐式推断：显式标签没给出 subject 或 chapter 时，从正文反推。
    # 不覆盖显式信息；只填补缺失项。这是把"自然语言旧日志"也能纳入按章
    # 聚类的关键路径。
    if not subject:
        inf_subject, inf_subgroup_canonical = _infer_subject_subgroup(content)
        if inf_subject:
            subject = inf_subject
            subgroup = inf_subgroup_canonical  # 直接用 canonical 形态
    if chapter_num is None and subject:
        canonical_sg = normalize_subgroup(subject, subgroup)
        chapter_num = _infer_chapter_num(content, subject, canonical_sg)

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
