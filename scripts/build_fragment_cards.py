#!/usr/bin/env python3
"""从到期簇生成只含 qid 与题面的每日碎片页，不修改卡片/SRS。"""
import argparse
import json
import re

from constants import DAILY_PLAN_RELATIVE_PATH
from daily_plan_state import parse_daily_plan
from env_util import atomic_write, json_error, resolve_obsidian_root
from metaskill_index import build_qid_to_cluster, load_index, qid_from_text
from study_ops import collect_due_cards, parse_today


def question_section(body):
    """保留原文（含公式、图片、子标题），遇到同级或更高标题立即停止。

    不复用 CLI payload：它会替换图片引用；也不读取解析区来补题面。
    """
    lines = []
    in_question = False
    fence = None
    for line in body.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            if in_question:
                lines.append(line)
            continue
        heading = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line) if fence is None else None
        if heading:
            if in_question and len(heading.group(1)) <= 3:
                break
            if not in_question and heading.group(1) == "###" and heading.group(2) == "题目":
                in_question = True
                continue
        if in_question:
            lines.append(line)
    # 未闭合代码块会吞掉后续标题，无法保证题面边界时跳过该卡。
    return "\n".join(lines).strip() if fence is None else ""


def current_plan_tasks(root, today):
    path = root / DAILY_PLAN_RELATIVE_PATH
    if not path.exists():
        return []
    plan = parse_daily_plan(path.read_text(encoding="utf-8"))
    return [task for task in plan["tasks"] if not task["done"]] if plan["date"] == today.isoformat() else []


def planned_cluster(cluster, qid, tasks, subject):
    if not cluster:
        return any(task["subject"] == subject and qid in task["block"] for task in tasks)
    # 簇 id/skill/ch 和具体 qid 均可出现在 AI 已落盘的任务及明细中。
    labels = [str(cluster.get(key) or "") for key in ("id", "skill", "ch")]
    qids = [f"qid-{str(value).removeprefix('qid-')}" for value in cluster.get("qids", [])]
    return any(task["subject"] == subject and any(
        label and label in task["block"] for label in [*labels, *qids, qid]) for task in tasks)


def build_fragment_cards(root, today, count=5):
    if count < 1:
        raise ValueError("count 必须大于 0")
    path = root / "碎片刷题" / f"{today.isoformat()}.md"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        return {"path": str(path), "created": False, "count": len(re.findall(r"^## qid-", text, re.M)),
                "message": "当日碎片页已存在，保留原文件"}
    tasks = current_plan_tasks(root, today)
    q2c = build_qid_to_cluster(load_index(root))
    candidates = []
    skipped = []
    seen = set()
    for card in collect_due_cards(root, today):
        qid = str(card["frontmatter"].get("question_id") or "")
        if not qid:
            suffix = qid_from_text(card["path"])
            qid = f"qid-{suffix}" if suffix else ""
        question = question_section(card["body"])
        if not qid or not question:
            skipped.append(card["path"])
            continue
        if qid in seen:
            continue
        seen.add(qid)
        cluster = q2c.get(qid.removeprefix("qid-")) or q2c.get(qid)
        preferred = planned_cluster(cluster, qid, tasks, card["subject"])
        # 沿用 SRS 的短间隔优先；相同间隔时更早到期的卡优先。
        rank = (not preferred, card["review_interval"], str(card["frontmatter"]["next_review"]), qid)
        candidates.append((rank, qid, question))
    selected = sorted(candidates)[:count]
    content = "\n\n".join(f"## {qid}\n\n### 题目\n{question}" for _, qid, question in selected)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, content + "\n" if content else "")
    result = {"path": str(path), "created": True, "count": len(selected),
              "qids": [qid for _, qid, _ in selected]}
    if not selected:
        result["message"] = "没有可用的到期题面，已生成空文件" if skipped else "没有到期卡，已生成空文件"
    if skipped:
        result["skipped"] = skipped
    return result


def main():
    parser = argparse.ArgumentParser(description="生成每日手机碎片刷题页")
    parser.add_argument("obsidian_root", nargs="?")
    parser.add_argument("--date", help="YYYY-MM-DD，默认今天")
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args()
    try:
        result = build_fragment_cards(resolve_obsidian_root(args.obsidian_root), parse_today(args.date), args.count)
    except (OSError, ValueError) as exc:
        json_error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
