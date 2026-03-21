#!/usr/bin/env python3
"""更新知识地图中指定考点的掌握度和备注。

用法: python3 update_knowledge_map.py [OBSIDIAN_ROOT] [科目] [考点关键词] [掌握度] [备注]
例:   python3 update_knowledge_map.py /path/to/root 数学一 二重积分 半会 "极坐标变换不熟"

匹配规则：
- 只匹配叶子考点行（以 "  " 缩进开头的行，如 "  05.5 二重积分"）
- 跳过章节标题行（含 ** 加粗标记的行，如 "**05 多元函数微积分**"）
- 关键词必须全部命中才算匹配
- 匹配多行时报错并列出候选，要求调用方提供更精确的关键词

科目映射: 数学一→数学一.md, 408→408.md, 政治→政治.md, 英语一→英语一.md
"""
import sys
from pathlib import Path

SUBJECT_MAP = {
    "数学一": "数学一.md", "数学": "数学一.md",
    "408": "408.md",
    "政治": "政治.md",
    "英语一": "英语一.md", "英语": "英语一.md",
}


def is_leaf_row(topic_cell):
    """判断是否为叶子考点行（非章节标题）。
    章节标题行含 ** 加粗标记，叶子行以数字编号开头（如 05.5）。"""
    stripped = topic_cell.strip()
    if "**" in stripped:
        return False
    if not stripped:
        return False
    return True


def main():
    if len(sys.argv) < 5:
        print("用法: python3 update_knowledge_map.py [OBSIDIAN_ROOT] [科目] [考点关键词] [掌握度] [备注(可选)]", file=sys.stderr)
        sys.exit(1)

    root = Path(sys.argv[1]) / "知识地图"
    subject = sys.argv[2]
    keyword = sys.argv[3]
    mastery = sys.argv[4]
    note = sys.argv[5] if len(sys.argv) > 5 else ""

    filename = SUBJECT_MAP.get(subject)
    if not filename:
        print(f"错误: 未知科目 '{subject}'，支持: {', '.join(SUBJECT_MAP.keys())}", file=sys.stderr)
        sys.exit(1)

    filepath = root / filename
    if not filepath.exists():
        print(f"错误: 文件不存在 {filepath}", file=sys.stderr)
        sys.exit(1)

    lines = filepath.read_text(encoding="utf-8").split("\n")
    keywords = [k.lower() for k in keyword.split()]

    # 第一遍：收集所有匹配的叶子行
    candidates = []
    for i, line in enumerate(lines):
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 5:
            continue
        topic_cell = cells[1]
        if not is_leaf_row(topic_cell):
            continue
        if all(kw in topic_cell.lower() for kw in keywords):
            candidates.append((i, topic_cell, cells))

    if len(candidates) == 0:
        print(f"警告: 未找到包含 '{keyword}' 的叶子考点行", file=sys.stderr)
        sys.exit(1)

    if len(candidates) > 1:
        print(f"错误: 关键词 '{keyword}' 匹配到 {len(candidates)} 行，请提供更精确的关键词:", file=sys.stderr)
        for _, topic, _ in candidates:
            print(f"  - {topic.strip()}", file=sys.stderr)
        sys.exit(1)

    # 精确匹配到一行，更新
    idx, topic_cell, cells = candidates[0]
    cells[2] = f" {mastery} "
    if note:
        cells[4] = f" {note} "
    lines[idx] = "|".join(cells)
    filepath.write_text("\n".join(lines), encoding="utf-8")
    print(f"已更新: {topic_cell.strip()} → 掌握度={mastery}" + (f", 备注={note}" if note else ""))


if __name__ == "__main__":
    main()
