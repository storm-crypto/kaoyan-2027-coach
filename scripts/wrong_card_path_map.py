"""错题卡 chapter 桶到多级目录路径的规范解析。

核心约束：已经配置规范多级目录的科目，不能把未知 chapter 原样落盘。
否则一次输入变体就会生成新的浅层目录。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from env_util import sanitize_path_segment

INVALID_PATH_CHARS_RE = re.compile(r'[\\/:*?"<>|]+')
WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class WrongCardChapterResolution:
    subject: str
    relative_dir: str
    chapter_path: str
    chapter_display: str
    chapter_id: str
    is_canonical: bool


WRONG_CARD_PATH_MAP: Dict[str, Dict[str, str]] = {
    "数学一": {
        "函数的性质与图形": "高等数学/01 第一章 函数、极限、连续/01 第一节 函数",
        "函数极限": "高等数学/01 第一章 函数、极限、连续/02 第二节 函数极限",
        "数列极限": "高等数学/01 第一章 函数、极限、连续/03 第三节 数列极限",
        "无穷小与无穷大的比较": "高等数学/01 第一章 函数、极限、连续/02 第二节 函数极限",
        "连续性与间断点分类": "高等数学/01 第一章 函数、极限、连续/04 第四节 函数的连续性",
        "导数定义与几何意义": "高等数学/02 第二章 导数与微分/01 第一节 导数与微分的相关概念",
        "求导法则与高阶导数": "高等数学/02 第二章 导数与微分/02 第二节 导数与微分的计算",
        "微分中值定理": "高等数学/03 第三章 微分中值定理与泰勒公式/02 第二节 拉格朗日中值定理",
        "洛必达法则与泰勒展开求极限": "高等数学/03 第三章 微分中值定理与泰勒公式/04 第四节 泰勒公式",
        "函数单调性、极值与最值": "高等数学/04 第四章 导数的应用/01 第一节 单调性与极值",
        "曲线凹凸性、拐点与渐近线": "高等数学/04 第四章 导数的应用/02 第二节 凹凸性与拐点",
        "不定积分计算": "高等数学/05 第五章 不定积分/02 第二节 不定积分的计算",
        "定积分的性质与计算": "高等数学/06 第六章 定积分及其应用/01 第一节 定积分的计算",
        "反常积分的判敛与计算": "高等数学/06 第六章 定积分及其应用/04 第四节 反常积分",
        "定积分的应用": "高等数学/06 第六章 定积分及其应用/05 第五节 定积分的应用",
        "多元函数极限与连续": "高等数学/08 第八章 多元函数微分学/01 第一节 多元函数微分学的基本概念",
        "偏导数与全微分": "高等数学/08 第八章 多元函数微分学/02 第二节 复合函数的偏导数和全微分",
        "复合函数与隐函数求导": "高等数学/08 第八章 多元函数微分学/03 第三节 隐函数微分法",
        "多元函数极值与条件极值": "高等数学/08 第八章 多元函数微分学/04 第四节 极值与最值",
        "二重积分": "高等数学/10 第十章 二重积分/02 第二节 二重积分的计算",
        "三重积分": "高等数学/13 第十三章 三重积分及第一型曲线、曲面积分/01 第一节 三重积分",
        "曲线积分": "高等数学/14 第十四章 第二型曲线、曲面积分/01 第一节 第二型曲线积分",
        "曲面积分": "高等数学/14 第十四章 第二型曲线、曲面积分/02 第二节 第二型曲面积分",
        "向量运算": "高等数学/11 第十一章 空间解析几何/01 第一节 向量代数",
        "平面方程与直线方程": "高等数学/11 第十一章 空间解析几何/02 第二节 平面方程与直线方程",
        "曲面方程与空间曲线": "高等数学/11 第十一章 空间解析几何/03 第三节 曲面方程",
        "常数项级数的判敛": "高等数学/12 第十二章 无穷级数/01 第一节 常数项级数",
        "幂级数的收敛域与求和": "高等数学/12 第十二章 无穷级数/02 第二节 幂级数",
        "函数展开为幂级数": "高等数学/12 第十二章 无穷级数/02 第二节 幂级数",
        "傅里叶级数": "高等数学/12 第十二章 无穷级数/03 第三节 傅里叶级数",
        "一阶微分方程": "高等数学/09 第九章 微分方程/02 第二节 一阶微分方程",
        "高阶线性微分方程": "高等数学/09 第九章 微分方程/04 第四节 高阶线性微分方程",
        "微分方程的应用": "高等数学/09 第九章 微分方程/01 第一节 微分方程的基本概念",
        "行列式的性质与计算": "线性代数/01 第一章 行列式/01 第一节 行列式的概念与性质",
        "按行列展开": "线性代数/01 第一章 行列式/01 第一节 行列式的概念与性质",
        "克拉默法则": "线性代数/01 第一章 行列式/02 第二节 克拉默法则",
        "矩阵运算与性质": "线性代数/02 第二章 矩阵/01 第一节 矩阵的概念与运算",
        "逆矩阵": "线性代数/02 第二章 矩阵/03 第三节 可逆矩阵",
        "初等变换与初等矩阵": "线性代数/02 第二章 矩阵/05 第五节 初等矩阵",
        "矩阵的秩": "线性代数/02 第二章 矩阵/04 第四节 矩阵的秩",
        "线性相关与线性无关": "线性代数/03 第三章 向量/02 第二节 向量组的线性相关性和线性表示",
        "向量组的秩": "线性代数/03 第三章 向量/02 第二节 向量组的线性相关性和线性表示",
        "向量空间": "线性代数/03 第三章 向量/04 第四节 $n$ 维向量空间(仅数学一要求)",
        "齐次方程组": "线性代数/04 第四章 线性方程组",
        "非齐次方程组": "线性代数/04 第四章 线性方程组",
        "方程组综合应用": "线性代数/04 第四章 线性方程组",
        "特征值与特征向量的求解": "线性代数/05 第五章 相似矩阵/01 第一节 特征值与特征向量",
        "相似矩阵与对角化": "线性代数/05 第五章 相似矩阵/02 第二节 矩阵相似",
        "实对称矩阵的正交对角化": "线性代数/05 第五章 相似矩阵/03 第三节 实对称矩阵",
        "二次型及其标准形": "线性代数/06 第六章 二次型/01 第一节 二次型的概念及其标准形",
        "正定二次型与正定矩阵": "线性代数/06 第六章 二次型/02 第二节 正定二次型与正定矩阵",
        "事件关系与概率公式": "概率论与数理统计/01 第一章 随机事件及其概率/03 第三节 概率计算公式",
        "条件概率与全概率贝叶斯": "概率论与数理统计/01 第一章 随机事件及其概率/03 第三节 概率计算公式",
        "事件独立性": "概率论与数理统计/01 第一章 随机事件及其概率/04 第四节 独立性和综合应用",
        "离散型随机变量及常见分布": "概率论与数理统计/02 第二章 一维随机变量及其分布/01 第一节 离散型随机变量及其概率分布",
        "连续型随机变量": "概率论与数理统计/02 第二章 一维随机变量及其分布/02 第二节 连续型随机变量及其分布",
        "分布函数与概率密度": "概率论与数理统计/02 第二章 一维随机变量及其分布/02 第二节 连续型随机变量及其分布",
        "随机变量函数的分布": "概率论与数理统计/02 第二章 一维随机变量及其分布/03 第三节 一维随机变量的函数分布",
        "联合分布与边缘分布": "概率论与数理统计/03 第三章 多维随机变量及其分布/01 第一节 二维随机变量",
        "条件分布与独立性": "概率论与数理统计/03 第三章 多维随机变量及其分布/02 第二节 独立性",
        "二维随机变量函数的分布": "概率论与数理统计/03 第三章 多维随机变量及其分布/03 第三节 多维随机变量的函数分布",
        "期望与方差": "概率论与数理统计/04 第四章 随机变量的数字特征/01 第一节 随机变量的数学期望与方差",
        "协方差与相关系数": "概率论与数理统计/04 第四章 随机变量的数字特征/02 第二节 协方差和相关系数",
        "大数定律": "概率论与数理统计/05 第五章 大数定律与中心极限定理/01 第一节 大数定律",
        "中心极限定理": "概率论与数理统计/05 第五章 大数定律与中心极限定理/02 第二节 中心极限定理",
        "三大抽样分布": "概率论与数理统计/06 第六章 数理统计的基本概念/02 第二节 抽样分布",
        "点估计": "概率论与数理统计/07 第七章 参数估计/01 第一节 点估计",
        "区间估计与假设检验": "概率论与数理统计/07 第七章 参数估计/03 第三节 区间估计(仅数学一要求)",
    }
}


def resolve_wrong_card_chapter(
    subject: str,
    chapter: str,
    *,
    strict: bool = True,
) -> WrongCardChapterResolution:
    """把用户传入的 chapter 解析为规范目录和稳定章节字段。

    strict=True 时，凡是有规范目录表的科目，未知 chapter 直接报错，避免
    `错题本/数学一/05.02...` 这类浅层目录再次被创建。
    """
    chapter_key = chapter.strip()
    subject_map = WRONG_CARD_PATH_MAP.get(subject, {})
    if not subject_map:
        return _generic_resolution(subject, chapter_key)

    normalized_chapter_key = "".join(chapter_key.split())
    alias_map = _build_alias_map(subject_map)
    if normalized_chapter_key in alias_map:
        _, relative_dir = alias_map[normalized_chapter_key]
        return _canonical_resolution(subject, relative_dir)

    if strict:
        suggestions = suggest_wrong_card_chapters(subject, chapter_key)
        suffix = f"。候选: {'；'.join(suggestions)}" if suggestions else ""
        raise ValueError(f"无法识别 {subject} 章节 '{chapter_key}'，拒绝按原文创建目录{suffix}")

    return _generic_resolution(subject, chapter_key)


def canonical_chapter_display(subject: str, relative_dir: str) -> str:
    """把落盘目录路径反解成规范叶子章节的 `chapter_display`；无法识别时返回 ""。

    供历史错题卡（frontmatter 没有 chapter_display 字段）在聚合时复用：
    `错题本/数学一/高等数学/05第五章.../02第二节...` 这类路径能反推出
    与新卡完全一致的 "05.02 第二节 ..."，避免同章节新旧卡在今日归档里分裂成两组。
    """
    resolution = resolve_wrong_card_chapter(subject, relative_dir, strict=False)
    return resolution.chapter_display if resolution.is_canonical else ""


def suggest_wrong_card_chapters(subject: str, chapter: str, limit: int = 8) -> List[str]:
    subject_map = WRONG_CARD_PATH_MAP.get(subject, {})
    if not subject_map:
        return []

    query = "".join(chapter.strip().split()).lower()
    candidates = []
    seen = set()
    for key, relative_dir in subject_map.items():
        display = _chapter_display_from_relative_dir(relative_dir)
        aliases = _aliases_for_entry(key, relative_dir)
        haystack = " ".join(aliases).lower()
        score = 0
        if query and query in haystack:
            score += 4
        if query and any(token and token in haystack for token in re.split(r"[.\s]+", query)):
            score += 1
        if score <= 0:
            continue
        if display in seen:
            continue
        seen.add(display)
        candidates.append((score, display))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    if not candidates:
        for _, relative_dir in list(subject_map.items())[:limit]:
            display = _chapter_display_from_relative_dir(relative_dir)
            if display not in seen:
                seen.add(display)
                candidates.append((0, display))
    return [display for _, display in candidates[:limit]]


def _generic_resolution(subject: str, chapter: str) -> WrongCardChapterResolution:
    chapter = chapter.strip()
    return WrongCardChapterResolution(
        subject=subject,
        relative_dir=chapter,
        chapter_path=_materialized_relative_dir(chapter),
        chapter_display=chapter,
        chapter_id="",
        is_canonical=False,
    )


def _canonical_resolution(subject: str, relative_dir: str) -> WrongCardChapterResolution:
    return WrongCardChapterResolution(
        subject=subject,
        relative_dir=relative_dir,
        chapter_path=_materialized_relative_dir(relative_dir),
        chapter_display=_chapter_display_from_relative_dir(relative_dir),
        chapter_id=_chapter_id_from_relative_dir(subject, relative_dir),
        is_canonical=True,
    )


def _build_alias_map(subject_map: Dict[str, str]) -> Dict[str, Tuple[str, str]]:
    alias_map: Dict[str, Tuple[str, str]] = {}
    for key, relative_dir in subject_map.items():
        for alias in _aliases_for_entry(key, relative_dir):
            normalized = "".join(alias.strip().split())
            if not normalized:
                continue
            existing = alias_map.get(normalized)
            if existing is not None and existing[1] != relative_dir:
                raise ValueError(
                    f"章节别名碰撞：归一化键 '{normalized}' 同时指向 "
                    f"'{existing[1]}'（来自 '{existing[0]}'）与 "
                    f"'{relative_dir}'（来自 '{key}'）；请消歧后再配置目录表"
                )
            alias_map.setdefault(normalized, (key, relative_dir))
    return alias_map


def _aliases_for_entry(key: str, relative_dir: str) -> List[str]:
    parts = list(Path(relative_dir).parts)
    aliases = [key, relative_dir, _materialized_relative_dir(relative_dir)]
    if parts:
        leaf = parts[-1].strip()
        leaf_without_num = re.sub(r"^\d{1,3}\s*", "", leaf).strip()
        leaf_without_section = _strip_section_prefix(leaf_without_num)
        aliases.extend([leaf, leaf_without_num, leaf_without_section])
        chapter_num = _leading_number(parts[-2]) if len(parts) >= 2 else None
        section_num = _leading_number(leaf)
        if chapter_num and section_num:
            aliases.append(f"{chapter_num}.{section_num} {leaf_without_num}")
            aliases.append(f"{chapter_num}.{section_num}{leaf_without_num}")
            aliases.append(f"{chapter_num}.{section_num} {leaf_without_section}")
            aliases.append(f"{chapter_num}.{section_num}{leaf_without_section}")
    return aliases


def _leading_number(text: str) -> Optional[str]:
    match = re.match(r"\s*(\d{1,3})", text)
    return match.group(1).zfill(2) if match else None


def _chapter_display_from_relative_dir(relative_dir: str) -> str:
    parts = list(Path(relative_dir).parts)
    if not parts:
        return ""
    leaf = parts[-1].strip()
    leaf_without_num = re.sub(r"^\d{1,3}\s*", "", leaf).strip()
    chapter_num = _leading_number(parts[-2]) if len(parts) >= 2 else None
    section_num = _leading_number(leaf)
    if chapter_num and section_num:
        return f"{chapter_num}.{section_num} {leaf_without_num}"
    return leaf_without_num or leaf


def _strip_section_prefix(text: str) -> str:
    return re.sub(r"^第[一二三四五六七八九十百零〇0-9]+节\s*", "", text).strip()


def _chapter_id_from_relative_dir(subject: str, relative_dir: str) -> str:
    subject_slug = {
        "数学一": "math1",
        "408": "408",
        "政治": "politics",
        "英语一": "english1",
    }.get(subject, subject)
    parts = list(Path(relative_dir).parts)
    subgroup = parts[0] if parts else ""
    subgroup_slug = {
        "高等数学": "gaoshu",
        "线性代数": "linear",
        "概率论与数理统计": "probability",
    }.get(subgroup, _safe_id_segment(subgroup))
    numbers = [_leading_number(part) for part in parts[1:]]
    number_parts = [number for number in numbers if number]
    return ":".join([subject_slug, subgroup_slug, *number_parts])


def _safe_id_segment(text: str) -> str:
    value = INVALID_PATH_CHARS_RE.sub("-", text.strip())
    value = WHITESPACE_RE.sub("-", value).strip("-")
    return value or "unknown"


def _materialized_relative_dir(relative_dir: str) -> str:
    return "/".join(sanitize_path_segment(part) for part in Path(relative_dir).parts)


# 旧通用考点桶名 -> 数学一知识地图的新李林叶子行名。
# 仅用于 update_knowledge_map.py 在数学一场景下做关键词归一化，
# 让历史调用方传入的旧桶名仍能命中新版知识地图。
#
# 标注规则：
# - 行尾 "# 挂靠" 注释表示这是"近似挂靠"而非严格 1:1 对应（旧桶语义比新李林节更宽或更窄，
#   或李林根本没有对应节，找最近的格子塞进去）。统计粒度会有轻微损耗，等需要时再细化。
# - 没有注释的行表示语义足够接近，可视为严格映射。
MATH1_KNOWLEDGE_MAP_ALIAS: Dict[str, str] = {
    "函数的性质与图形": "01.01 第一节 函数",                              # 挂靠：旧桶含周期性/奇偶性等图形性质，李林 01.01 只叫"函数"
    "函数极限": "01.02 第二节 函数极限",
    "数列极限": "01.03 第三节 数列极限",
    "无穷小与无穷大的比较": "01.02 第二节 函数极限",                       # 挂靠：李林无独立"无穷小比较"节，塞进函数极限
    "连续性与间断点分类": "01.04 第四节 函数的连续性",
    "导数定义与几何意义": "02.01 第一节 导数与微分的相关概念",
    "求导法则与高阶导数": "02.02 第二节 导数与微分的计算",                 # 挂靠：旧桶涵盖"高阶导"，李林 02.02 是通用"导数计算"
    "微分中值定理": "03.02 第二节 拉格朗日中值定理",                       # 挂靠：旧桶涵盖罗尔/拉格朗日/柯西/泰勒四个，李林拆 03.01-03.04，挂最常用的拉格朗日
    "洛必达法则与泰勒展开求极限": "03.04 第四节 泰勒公式",
    "函数单调性、极值与最值": "04.01 第一节 单调性与极值",
    "曲线凹凸性、拐点与渐近线": "04.02 第二节 凹凸性与拐点",               # 挂靠：旧桶含"渐近线"，李林 04.02 只叫"凹凸性与拐点"
    "不定积分计算": "05.02 第二节 不定积分的计算",
    "定积分的性质与计算": "06.01 第一节 定积分的计算",                     # 挂靠：旧桶含"性质"，李林 06 章无独立"性质"节
    "反常积分的判敛与计算": "06.04 第四节 反常积分",
    "定积分的应用": "06.05 第五节 定积分的应用",
    "多元函数极限与连续": "08.01 第一节 多元函数微分学的基本概念",         # 挂靠：李林无独立"多元极限与连续"节
    "偏导数与全微分": "08.02 第二节 复合函数的偏导数和全微分",             # 挂靠：李林 08.02 强调"复合"，旧桶更通用
    "复合函数与隐函数求导": "08.03 第三节 隐函数微分法",                   # 挂靠：旧桶含复合（实际属 08.02）+ 隐函数，挂 08.03 隐函数
    "多元函数极值与条件极值": "08.04 第四节 极值与最值",                   # 挂靠：旧桶专指拉格朗日条件极值，李林 08.04 是通用极值最值
    "二重积分": "10.02 第二节 二重积分的计算",                              # 挂靠：旧桶涵盖整章，李林 10 章 4 节，挂"计算"节
    "三重积分": "13.01 第一节 三重积分",                                    # 挂靠：李林 ch13 共 3 节，旧桶就一个，挂第一节
    "曲线积分": "14.01 第一节 第二型曲线积分",                              # 挂靠：旧桶含第一/二型，李林分 13.02 一型 + 14.01 二型，挂二型
    "曲面积分": "14.02 第二节 第二型曲面积分",                              # 挂靠：同曲线积分
    "向量运算": "11.01 第一节 向量代数",                                    # 挂靠：旧桶限"点积/叉积/混合积"，李林 11.01 更宽
    "平面方程与直线方程": "11.02 第二节 平面方程与直线方程",
    "曲面方程与空间曲线": "11.03 第三节 曲面方程",                          # 挂靠：李林无独立"空间曲线"节
    "常数项级数的判敛": "12.01 第一节 常数项级数",
    "幂级数的收敛域与求和": "12.02 第二节 幂级数",
    "函数展开为幂级数": "12.02 第二节 幂级数",                              # 挂靠：与上条同节，李林无独立"展开"节
    "傅里叶级数": "12.03 第三节 傅里叶级数",
    "一阶微分方程": "09.02 第二节 一阶微分方程",
    "高阶线性微分方程": "09.04 第四节 高阶线性微分方程",
    "微分方程的应用": "09.01 第一节 微分方程的基本概念",                    # 挂靠：李林 ch9 无独立"应用"节，挂"基本概念"是 weak
    "行列式的性质与计算": "01.01 第一节 行列式的概念与性质",                # 挂靠：旧桶含"计算"，李林 01.01 是"概念与性质"
    "按行列展开": "01.01 第一节 行列式的概念与性质",                        # 挂靠：按行列展开是计算方法，李林归 01.01
    "克拉默法则": "01.02 第二节 克拉默法则",
    "矩阵运算与性质": "02.01 第一节 矩阵的概念与运算",                      # 挂靠：旧桶含通用"性质"，李林 02.01 限"概念与运算"，其它性质散在 02.02-02.06
    "逆矩阵": "02.03 第三节 可逆矩阵",
    "初等变换与初等矩阵": "02.05 第五节 初等矩阵",                          # 挂靠：旧桶含"初等变换"，李林 02.05 限"初等矩阵"
    "矩阵的秩": "02.04 第四节 矩阵的秩",
    "线性相关与线性无关": "03.02 第二节 向量组的线性相关性和线性表示",
    "向量组的秩": "03.02 第二节 向量组的线性相关性和线性表示",              # 挂靠：与上条同节，李林无独立"秩"节
    "向量空间": "03.04 第四节 n 维向量空间",
    "齐次方程组": "04.01 第一节 齐次线性方程组",
    "非齐次方程组": "04.02 第二节 非齐次线性方程组",
    "方程组综合应用": "04.03 第三节 线性方程组的综合应用",
    "特征值与特征向量的求解": "05.01 第一节 特征值与特征向量",
    "相似矩阵与对角化": "05.02 第二节 矩阵相似",                            # 挂靠：旧桶含"对角化"，李林 05.02 限"矩阵相似"
    "实对称矩阵的正交对角化": "05.03 第三节 实对称矩阵",                    # 挂靠：旧桶限"正交对角化"，李林 05.03 是通用"实对称矩阵"
    "二次型及其标准形": "06.01 第一节 二次型的概念及其标准形",
    "正定二次型与正定矩阵": "06.02 第二节 正定二次型与正定矩阵",
    "事件关系与概率公式": "01.03 第三节 概率计算公式",                      # 挂靠：旧桶含"事件关系"，李林 01 章有 01.01 运算/01.02 定义/01.03 公式，挂 01.03
    "条件概率与全概率贝叶斯": "01.03 第三节 概率计算公式",
    "事件独立性": "01.04 第四节 独立性和综合应用",
    "离散型随机变量及常见分布": "02.01 第一节 离散型随机变量及其概率分布",
    "连续型随机变量": "02.02 第二节 连续型随机变量及其分布",
    "分布函数与概率密度": "02.02 第二节 连续型随机变量及其分布",            # 挂靠：分布函数离散/连续都有，挂连续型因大头在 02.02
    "随机变量函数的分布": "02.03 第三节 一维随机变量的函数分布",
    "联合分布与边缘分布": "03.01 第一节 二维随机变量",                      # 挂靠：旧桶含"边缘"，李林 03.01 是"二维"
    "条件分布与独立性": "03.02 第二节 独立性",                              # 挂靠：旧桶含"条件分布"（实际属 03.01 二维），但强调独立性挂 03.02
    "二维随机变量函数的分布": "03.03 第三节 多维随机变量的函数分布",
    "期望与方差": "04.01 第一节 随机变量的数学期望与方差",
    "协方差与相关系数": "04.02 第二节 协方差和相关系数",
    "大数定律": "05.01 第一节 大数定律",
    "中心极限定理": "05.02 第二节 中心极限定理",
    "三大抽样分布": "06.02 第二节 抽样分布",
    "点估计": "07.01 第一节 点估计",
    "区间估计与假设检验": "07.03 第三节 区间估计",                          # 挂靠：旧桶含假设检验，李林独立 ch8 假设检验；挂 07.03 是 weak
}


def resolve_math1_knowledge_map_alias(keyword: str) -> str:
    """把数学一旧通用考点桶名翻译为新李林叶子行名；未命中则原样返回。"""
    return MATH1_KNOWLEDGE_MAP_ALIAS.get(keyword.strip(), keyword)
