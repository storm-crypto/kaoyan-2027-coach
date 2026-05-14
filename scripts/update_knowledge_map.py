#!/usr/bin/env python3
"""更新知识地图中指定考点的掌握度和备注。

用法（位置参数，向后兼容）:
  python3 update_knowledge_map.py [OBSIDIAN_ROOT] [科目] [考点关键词] [掌握度] [备注...]
  环境变量 KAOYAN_OBSIDIAN_ROOT 可替代 CLI 参数

推荐新用法（结构化卡点）:
  python3 update_knowledge_map.py [OBSIDIAN_ROOT] [科目] [考点关键词] [掌握度] \
      --finding-add "qid-xxxxxxxxxxxx|YYYY-MM-DD|一句话卡点描述" \
      [--finding-add ...] [--keep-legacy-note] \
      [--fold-threshold 3] [--mastery-threshold-days 14]

匹配规则：
- 只匹配叶子考点行（非 ** 加粗标题行）
- 关键词必须全部命中才算匹配
- 匹配多行时报错并列出候选

备注字段（cells[4]）写入规则（ccce449 之后再次升级）：
- 优先解析为结构化 Finding 列表（每条 = qid + 暴露日期 + 描述 + 掌握日期?）
- `--finding-add` 按 qid 去重合并；同时自动扫错题本，把 review_interval ≥ 阈值的条目划掉
- 老的自由文本备注默认在首次写新格式时丢弃；`--keep-legacy-note` 可保留
- 没有任何 `--finding-add` 时：仍跑一次自动划掉同步，不动结构
- 位置参数里的 NOTE（旧用法）仅在没有任何 `--finding-add` 且没有现有 findings 时生效，整段覆盖
"""
import argparse
import json
import sys
from pathlib import Path

from env_util import resolve_obsidian_root, atomic_write
from knowledge_findings import (
    DEFAULT_FOLD_THRESHOLD,
    DEFAULT_MASTERY_THRESHOLD_DAYS,
    Finding,
    merge_findings,
    parse_findings,
    render_findings,
    sync_mastered_status,
)
from study_ops import parse_today

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


def _split_optionals(argv):
    """从 argv 中抽出 optional 参数，剩下的当位置参数返回。"""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--finding-add",
        action="append",
        default=[],
        help='新增/更新一条结构化卡点，格式 "qid|YYYY-MM-DD|描述"，可重复',
    )
    parser.add_argument("--keep-legacy-note", action="store_true", default=False)
    parser.add_argument("--fold-threshold", type=int, default=DEFAULT_FOLD_THRESHOLD)
    parser.add_argument(
        "--mastery-threshold-days",
        type=int,
        default=DEFAULT_MASTERY_THRESHOLD_DAYS,
    )
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    known, remaining = parser.parse_known_args(argv)
    return known, remaining


def _parse_finding_add(raw):
    """把 "qid|YYYY-MM-DD|描述" 拆为 (qid, date_str, desc)。"""
    parts = [p.strip() for p in raw.split("|", 2)]
    if len(parts) != 3 or not all(parts):
        print(json.dumps({
            "error": True,
            "message": f"--finding-add 格式错误：{raw}（应为 qid|YYYY-MM-DD|描述）",
        }, ensure_ascii=False))
        sys.exit(1)
    return parts[0], parts[1], parts[2]


def main():
    opts, remaining = _split_optionals(sys.argv[1:])
    args = remaining

    if len(args) < 3:
        print(json.dumps({
            "error": True,
            "message": "用法: python3 update_knowledge_map.py [OBSIDIAN_ROOT] [科目] [考点关键词] [掌握度] [备注(可选)]",
        }, ensure_ascii=False))
        sys.exit(1)

    if args[0] in SUBJECT_MAP:
        root = resolve_obsidian_root(None) / "知识地图"
        subject, keyword, mastery = args[0], args[1], args[2]
        note = " ".join(args[3:]).strip()
    else:
        if len(args) < 4:
            print(json.dumps({
                "error": True,
                "message": "用法: python3 update_knowledge_map.py [OBSIDIAN_ROOT] [科目] [考点关键词] [掌握度] [备注(可选)]",
            }, ensure_ascii=False))
            sys.exit(1)
        root = resolve_obsidian_root(args[0]) / "知识地图"
        subject, keyword, mastery = args[1], args[2], args[3]
        note = " ".join(args[4:]).strip()

    filename = SUBJECT_MAP.get(subject)
    if not filename:
        print(json.dumps({
            "error": True,
            "message": f"未知科目 '{subject}'，支持: {', '.join(SUBJECT_MAP.keys())}",
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

    candidates = find_candidates(aliased_keyword)
    keyword_used = aliased_keyword
    if not candidates and aliased_keyword != keyword:
        candidates = find_candidates(keyword)
        keyword_used = keyword

    if len(candidates) == 0:
        print(json.dumps({
            "error": True,
            "message": f"未找到包含 '{keyword_used}' 的叶子考点行",
        }, ensure_ascii=False))
        sys.exit(1)

    if len(candidates) > 1:
        print(json.dumps({
            "error": True,
            "message": f"关键词 '{keyword_used}' 匹配到 {len(candidates)} 行，请提供更精确的关键词",
            "candidates": [topic.strip() for _, topic, _ in candidates],
        }, ensure_ascii=False))
        sys.exit(1)

    idx, topic_cell, cells = candidates[0]
    new_mastery = mastery.strip()
    topic = cells[1].strip()
    confidence = cells[3].strip()
    existing_note = cells[4].strip()

    obsidian_root = filepath.parent.parent

    findings, legacy_text = parse_findings(existing_note)
    using_findings_mode = bool(opts.finding_add) or bool(findings)

    new_note: str
    if using_findings_mode:
        today_obj = parse_today(opts.today)
        for raw in opts.finding_add:
            qid, date_str, desc = _parse_finding_add(raw)
            try:
                from datetime import date as _date
                d = _date.fromisoformat(date_str) if date_str else today_obj
            except ValueError:
                print(json.dumps({
                    "error": True,
                    "message": f"--finding-add 日期格式错误：{date_str}",
                }, ensure_ascii=False))
                sys.exit(1)
            findings = merge_findings(findings, qid, d, desc)

        findings = sync_mastered_status(
            findings,
            obsidian_root,
            threshold_days=opts.mastery_threshold_days,
        )
        rendered = render_findings(findings, fold_threshold=opts.fold_threshold)
        if opts.keep_legacy_note and legacy_text:
            new_note = f"{rendered}<br>{legacy_text}" if rendered else legacy_text
        else:
            new_note = rendered
        # 位置参数里传的 NOTE 在 findings 模式下被忽略（避免双语义）
    else:
        # 旧行为：直接用位置参数 NOTE 整段覆盖
        new_note = note if note else existing_note

    lines[idx] = f"| {topic} | {new_mastery} | {confidence} | {new_note} |"
    atomic_write(filepath, "\n".join(lines))
    print(json.dumps({
        "updated": topic_cell.strip(),
        "mastery": mastery,
        "note": new_note,
        "finding_count": len(findings) if using_findings_mode else 0,
        "mastered_count": sum(1 for f in findings if f.mastered_at) if using_findings_mode else 0,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
