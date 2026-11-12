#!/usr/bin/env python3
"""扫描错题本，返回今日到期的待复习错题（JSON）。
默认只读；显式 --apply-overdue 才将超期 7 天以上卡片的 review_interval 重置为 1。

用法: python3 scan_due_reviews.py [OBSIDIAN_ROOT] [--today YYYY-MM-DD] [--plain] [--by-cluster] [--apply-overdue]
      环境变量 KAOYAN_OBSIDIAN_ROOT 可替代 CLI 参数

--by-cluster: 额外返回 `clusters` 字段，把到期卡按 `错题本/_元技能索引.json` 的元技能簇
分组，并按「每小时能清掉几张到期卡」降序排。到期量大时（> 30 道）应优先用这个视图，
逐卡线性过 300 道赶不上考试。`due` 字段始终保留，向后兼容。
"""
import argparse
import json
from typing import Tuple

from archive_ops import extract_heading_block
from frontmatter import serialize_frontmatter
from env_util import atomic_write, resolve_obsidian_root
from figure_ops import replace_figure_embeds_for_cli
from latex_to_unicode import latex_to_unicode
from metaskill_index import group_due_by_cluster, load_index
from study_ops import iter_review_cards, parse_today, review_schedule_state

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
    question_text = replace_figure_embeds_for_cli(
        normalize_block(extract_heading_block(body, "题目", level=3))
    )
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
    parser.add_argument("--apply-overdue", action="store_true",
                        help="显式应用超期重排：间隔重置为 1，复习日设为今天；不改变掌握度或历史")
    args = parser.parse_args()

    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    today = parse_today(args.today)
    due = []
    degraded = 0
    pending_overdue = 0
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

        schedule = review_schedule_state(next_review, interval, today)
        # 仅显式请求才重排；普通扫描不改变任何学习记录。
        if schedule["overdue_reset_pending"] and args.apply_overdue:
            fm["review_interval"] = "1"
            fm["next_review"] = today.isoformat()
            interval = 1
            next_review = today
            atomic_write(item["path"], serialize_frontmatter(fm, key_order, body))
            degraded += 1
            schedule = review_schedule_state(next_review, interval, today)
        if schedule["overdue_reset_pending"]:
            pending_overdue += 1

        if schedule["due"]:
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
                "next_review": next_review.isoformat(),
                "overdue_days": schedule["overdue_days"],
                "overdue_reset_pending": schedule["overdue_reset_pending"],
                "filename": item["path"].stem,
                "question_text": question_text,
                "options_text": options_text,
                "question_preview": question_preview,
            })

    due.sort(key=lambda x: (x["review_interval"], x["subject"]))
    result = {"due": due, "degraded": degraded, "pending_overdue": pending_overdue}
    if pending_overdue:
        result["overdue_warning"] = (
            f"{pending_overdue} 张卡超期超过 7 天，当前扫描未改写排期；"
            "如需将间隔重置为 1 天，请显式使用 --apply-overdue。"
        )
    if args.by_cluster:
        index = load_index(obsidian_root)
        result["clusters"] = group_due_by_cluster(due, index)
        if not index.get("clusters"):
            result["cluster_warning"] = (
                "未找到可用的 错题本/_元技能索引.json，"
                "到期题已保留在未归簇分组；补齐索引后可按元技能浏览。"
            )
    if icloud_warnings:
        result["icloud_placeholders"] = icloud_warnings
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
