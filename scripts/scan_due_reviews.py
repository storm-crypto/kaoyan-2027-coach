#!/usr/bin/env python3
"""扫描错题本，返回今日到期的待复习错题（JSON）。
同时对超期 7 天以上的卡片自动将 review_interval 重置为 1。

用法: python3 scan_due_reviews.py [OBSIDIAN_ROOT] [--today YYYY-MM-DD] [--plain] [--by-cluster]
      环境变量 KAOYAN_OBSIDIAN_ROOT 可替代 CLI 参数

--by-cluster: 额外返回 `clusters` 字段，把到期卡按 `错题本/_元技能索引.json` 的元技能簇
分组，并按「每小时能清掉几张到期卡」降序排。到期量大时（> 30 道）应优先用这个视图，
逐卡线性过 300 道赶不上考试。`due` 字段始终保留，向后兼容。
"""
import argparse
import json
from datetime import timedelta
from typing import Tuple

from archive_ops import extract_heading_block
from constants import SRS_GRADUATED_INTERVAL_DAYS, SRS_OVERDUE_DEGRADE_DAYS
from frontmatter import serialize_frontmatter
from env_util import atomic_write, resolve_obsidian_root
from latex_to_unicode import latex_to_unicode
from metaskill_index import group_due_by_cluster, load_index
from study_ops import iter_review_cards, parse_today

from constants import QUESTION_PREVIEW_LINE_LIMIT


def normalize_block(text: str) -> str:
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def merge_question_and_legacy_options(question_text: str, options_text: str) -> str:
    if not options_text:
        return question_text
    if not question_text:
        return options_text
    return f"{question_text}\n{options_text}"


def build_question_payload(body: str, topic: str) -> Tuple[str, str, str]:
    """从卡片正文构造 (question_text, options_text, preview)。

    字段语义（ccce449 之后）：
    - `question_text`：题目正文，含选项。新卡选项直接写在 `### 题目` 区块里；
      老卡若仍保留独立的 `### 选项（如有）` 区块，会被自动拼到题目末尾，
      所以调用方拿到的 `question_text` 已经是完整可读题面，不需要再拼
      `options_text`。
    - `options_text`：仅对老卡（仍有 `### 选项（如有）` 区块）非空，新卡固定为 ""。
      保留字段是为了向后兼容直接消费它的下游；新代码不应再依赖它。
    - `preview`：基于 merged 题面取前 N 行，给 CLI/对话框预览用。
    """
    question_text = normalize_block(extract_heading_block(body, "题目", level=3))
    options_text = normalize_block(extract_heading_block(body, "选项（如有）", level=3))
    merged_question_text = merge_question_and_legacy_options(question_text, options_text)
    preview_source = merged_question_text or topic or "未记录题目"
    preview = "\n".join(preview_source.splitlines()[:QUESTION_PREVIEW_LINE_LIMIT])
    return merged_question_text, options_text, preview


def main() -> None:
    parser = argparse.ArgumentParser(description="扫描到期错题")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    parser.add_argument("--plain", action="store_true",
                        help="将 LaTeX 公式转为 Unicode 可读文本（适用于 CLI 环境）")
    parser.add_argument("--by-cluster", dest="by_cluster", action="store_true",
                        help="额外按元技能簇分组并按每小时清卡数排序")
    args = parser.parse_args()

    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    today = parse_today(args.today)
    threshold = today - timedelta(days=SRS_OVERDUE_DEGRADE_DAYS)
    due = []
    degraded = 0
    icloud_warnings = []

    for item in iter_review_cards(obsidian_root):
        if item["icloud_placeholder"]:
            icloud_warnings.append(str(item["path"]))
            continue

        fm = item["frontmatter"]
        body = item["body"]
        key_order = item["key_order"]
        next_review = item["next_review"]
        interval = item["review_interval"]
        if not fm or next_review is None or interval is None:
            continue

        # 超期降级：interval 重置为 1，next_review 设为今天
        if next_review < threshold and interval > 1:
            fm["review_interval"] = "1"
            fm["next_review"] = today.isoformat()
            interval = 1
            next_review = today
            atomic_write(item["path"], serialize_frontmatter(fm, key_order, body))
            degraded += 1

        # 筛选到期且未毕业（interval < 90）
        if next_review <= today and interval < SRS_GRADUATED_INTERVAL_DAYS:
            topic = fm.get("topic", "")
            question_text, options_text, question_preview = build_question_payload(body, topic)
            if args.plain:
                question_text = latex_to_unicode(question_text)
                options_text = latex_to_unicode(options_text)
                question_preview = latex_to_unicode(question_preview)
            due.append({
                "path": str(item["path"]),
                "subject": item["subject"],
                "topic": topic,
                "status": fm.get("status", ""),
                "review_interval": interval,
                "filename": item["path"].stem,
                "question_text": question_text,
                "options_text": options_text,
                "question_preview": question_preview,
            })

    due.sort(key=lambda x: (x["review_interval"], x["subject"]))
    result = {"due": due, "degraded": degraded}
    if args.by_cluster:
        index = load_index(obsidian_root)
        if index.get("clusters"):
            result["clusters"] = group_due_by_cluster(due, index)
        else:
            result["clusters"] = []
            result["cluster_warning"] = (
                "未找到 错题本/_元技能索引.json，已退化为扁平模式；"
                "先建索引再用 --by-cluster"
            )
    if icloud_warnings:
        result["icloud_placeholders"] = icloud_warnings
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
