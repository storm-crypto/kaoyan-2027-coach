#!/usr/bin/env python3
"""更新知识地图中指定考点的掌握度和备注。

用法: python3 update_knowledge_map.py [OBSIDIAN_ROOT] [科目] [考点关键词] [掌握度] [备注...]
      环境变量 KAOYAN_OBSIDIAN_ROOT 可替代 CLI 参数
例:   python3 update_knowledge_map.py /path/to/root 数学一 二重积分 半会 "极坐标变换不熟"

匹配规则：
- 只匹配叶子考点行（非 ** 加粗标题行）
- 关键词必须全部命中才算匹配
- 匹配多行时报错并列出候选
"""
import json
import sys
from pathlib import Path

from env_util import resolve_obsidian_root, atomic_write

SUBJECT_MAP = {
    "数学一": "数学一.md", "数学": "数学一.md",
    "408": "408.md",
    "政治": "政治.md",
    "英语一": "英语一.md", "英语": "英语一.md",
}


def is_leaf_row(topic_cell):
    """判断是否为叶子考点行（非章节标题）。"""
    stripped = topic_cell.strip()
    if not stripped or "**" in stripped:
        return False
    return True


def main():
    # 智能参数解析：第一个参数如果是已知科目名，则 OBSIDIAN_ROOT 从环境变量读取
    args = sys.argv[1:]
    if len(args) < 3:
        print(json.dumps({
            "error": True,
            "message": "用法: python3 update_knowledge_map.py [OBSIDIAN_ROOT] [科目] [考点关键词] [掌握度] [备注(可选)]"
        }, ensure_ascii=False))
        sys.exit(1)

    # 如果第一个参数是已知科目，说明省略了 OBSIDIAN_ROOT
    if args[0] in SUBJECT_MAP:
        root = resolve_obsidian_root(None) / "知识地图"
        subject, keyword, mastery = args[0], args[1], args[2]
        note = " ".join(args[3:]).strip()
    else:
        if len(args) < 4:
            print(json.dumps({
                "error": True,
                "message": "用法: python3 update_knowledge_map.py [OBSIDIAN_ROOT] [科目] [考点关键词] [掌握度] [备注(可选)]"
            }, ensure_ascii=False))
            sys.exit(1)
        root = resolve_obsidian_root(args[0]) / "知识地图"
        subject, keyword, mastery = args[1], args[2], args[3]
        note = " ".join(args[4:]).strip()

    filename = SUBJECT_MAP.get(subject)
    if not filename:
        print(json.dumps({
            "error": True,
            "message": f"未知科目 '{subject}'，支持: {', '.join(SUBJECT_MAP.keys())}"
        }, ensure_ascii=False))
        sys.exit(1)

    filepath = root / filename
    if not filepath.exists():
        print(json.dumps({"error": True, "message": f"文件不存在: {filepath}"}, ensure_ascii=False))
        sys.exit(1)

    if subject in {"数学一", "数学"}:
        from wrong_card_path_map import resolve_math1_knowledge_map_alias
        aliased_keyword = resolve_math1_knowledge_map_alias(keyword)
    else:
        aliased_keyword = keyword

    lines = filepath.read_text(encoding="utf-8").split("\n")

    def find_candidates(query):
        kws = [k.lower() for k in query.split()]
        out = []
        for i, line in enumerate(lines):
            if "|" not in line:
                continue
            cells = [c.strip() for c in line.split("|")]
            if len(cells) < 5:
                continue
            topic_cell = cells[1]
            if not is_leaf_row(topic_cell):
                continue
            if all(kw in topic_cell.lower() for kw in kws):
                out.append((i, topic_cell, cells))
        return out

    # 先按 alias 后的关键词匹配；命中不为 0 时直接采用。
    # 否则回退到原始关键词，让仍在使用旧结构的知识地图也能命中。
    candidates = find_candidates(aliased_keyword)
    keyword_used = aliased_keyword
    if not candidates and aliased_keyword != keyword:
        candidates = find_candidates(keyword)
        keyword_used = keyword

    if len(candidates) == 0:
        print(json.dumps({
            "error": True,
            "message": f"未找到包含 '{keyword_used}' 的叶子考点行"
        }, ensure_ascii=False))
        sys.exit(1)

    if len(candidates) > 1:
        print(json.dumps({
            "error": True,
            "message": f"关键词 '{keyword_used}' 匹配到 {len(candidates)} 行，请提供更精确的关键词",
            "candidates": [topic.strip() for _, topic, _ in candidates]
        }, ensure_ascii=False))
        sys.exit(1)

    idx, topic_cell, cells = candidates[0]
    cells[2] = f" {mastery} "
    if note:
        cells[4] = f" {note} "
    lines[idx] = "|".join(cells)
    atomic_write(filepath, "\n".join(lines))
    print(json.dumps({
        "updated": topic_cell.strip(),
        "mastery": mastery,
        "note": note,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
