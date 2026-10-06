"""工作台的只读投影：计划、到期复习、知识证据与今日收尾。"""
from collections import Counter
from datetime import timedelta
from pathlib import Path
import re

from archive_ops import extract_heading_block
from build_knowledge_test import parse_knowledge_map
from constants import DAILY_PLAN_RELATIVE_PATH, PLAN_SUBJECTS
from daily_plan_state import parse_daily_plan
from knowledge_findings import parse_findings
from log_layout import log_path_for
from metaskill_index import group_due_by_cluster, load_index
from open_in_obsidian import build_uris, find_vault_root
from textbook_progress import build_plan_items, load_week_textbook_rows, week_plan_path


def read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def make_link(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if not path.is_file():
        return None
    vault, _ = find_vault_root(root, root)
    try:
        return {"path": str(path), "uri": build_uris(path, vault, vault.name)["uri"]}
    except ValueError:
        return None


def collect_week(root, today):
    path = week_plan_path(root, today)
    text = read_text(path)
    goals = []
    for line in extract_heading_block(text, "科目分配").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[0] in PLAN_SUBJECTS:
            goals.append({"subject": cells[0], "goal": cells[3]})
    _, rows = load_week_textbook_rows(root, today) if text else (path, [])
    textbooks = [{
        "name": item.name, "current": item.row.current or item.row.start,
        "end": item.row.end, "done": item.done, "note": item.note,
        "today_pages": item.today_pages,
    } for item in build_plan_items(rows, today)]
    return {"link": make_link(path, root), "goals": goals, "textbooks": textbooks}


def collect_review_groups(root, today, cards, focus):
    due = [card for card in cards if card["is_due"]]
    grouped = group_due_by_cluster(due, load_index(root))
    groups = []
    for group in grouped:
        # 尚未归簇的卡也按章节聚合，避免把整库塞进一个任务。
        buckets = {}
        for card in group["cards"]:
            key = (card["subject"], card["chapter"]) if group["cluster_id"] == "unclustered" else (card["subject"], group["cluster_id"])
            buckets.setdefault(key, []).append(card)
        for (subject, _), members in buckets.items():
            failed = sum(card["recent_failures"] >= 2 for card in members)
            weak = sum(card["status"] in {"不会", "半会"} for card in members)
            focused = any(subject in item or (subject == "数学一" and "数学" in item) or (subject == "英语一" and "英语" in item) for item in focus)
            overdue = max(card["overdue_days"] or 0 for card in members)
            reasons = []
            if failed:
                reasons.append(f"{failed} 道题在近 30 天多次答错")
            if focused:
                reasons.append("所在科目列入当前聚焦问题")
            if weak:
                reasons.append(f"{weak} 道题仍记录为不会或半会")
            reasons.append(f"最久超期 {overdue} 天" if overdue else "今天到期")
            # 先反复失分和现有重点，再看薄弱/超期；不估算不存在的提分收益。
            priority = (bool(failed), focused, bool(weak), overdue)
            members = sorted(members, key=lambda card: (-card["recent_failures"], card["status"] == "会", -(card["overdue_days"] or 0), card["path"]))
            groups.append({
                "subject": subject, "chapter": members[0]["chapter"],
                "count": len(members), "cluster_id": group["cluster_id"],
                "reasons": reasons, "priority": priority,
                "cards": [{
                    "topic": card["topic"], "question_id": card["question_id"],
                    "status": card["status"], "last_review": card["last_review_at"],
                    "next_review": card["next_review"], "link": make_link(card["path"], root),
                    "command": f"/review {card['question_id']}" if card["question_id"] else f"/review {card['subject']} {card['topic']}",
                } for card in members],
            })
    return sorted(groups, key=lambda group: group["priority"], reverse=True)


def collect_knowledge(root, cards):
    by_qid = {card["question_id"]: card for card in cards if card["question_id"]}
    subjects = []
    for subject in PLAN_SUBJECTS:
        path = root / "知识地图" / f"{subject}.md"
        chapters = {}
        if path.is_file():
            for row in parse_knowledge_map(path):
                key = (row["module"], row["chapter"] or "未分章")
                chapter = chapters.setdefault(key, {"module": key[0], "name": key[1], "topics": []})
                findings, legacy = parse_findings(row["note"])
                evidence = []
                for finding in findings:
                    card = by_qid.get(finding.qid)
                    evidence.append({
                        "description": finding.description,
                        "date": finding.first_exposed.isoformat(),
                        "resolved": finding.mastered_at.isoformat() if finding.mastered_at else None,
                        "last_review": card["last_review_at"] if card else None,
                        "link": make_link(card["path"], root) if card else None,
                    })
                chapter["topics"].append({
                    "name": row["topic"], "status": row["mastery"] if row["mastery"] in {"会", "半会", "不会"} else "待测",
                    "evidence": evidence, "note": legacy,
                    "command": f"/test {subject} {row['module']} {row['topic']}",
                })
        for chapter in chapters.values():
            chapter["counts"] = dict(Counter(topic["status"] for topic in chapter["topics"]))
        subjects.append({"subject": subject, "link": make_link(path, root), "chapters": list(chapters.values())})
    return subjects


def build_workbench(root, today, cards, archive, logs):
    root = Path(root).resolve()
    plan_path = root / DAILY_PLAN_RELATIVE_PATH
    plan = parse_daily_plan(read_text(plan_path))
    plan["link"] = make_link(plan_path, root)
    plan["current"] = plan["date"] == today.isoformat()
    plan["done"] = sum(task["done"] for task in plan["tasks"]) if plan["current"] else 0
    plan["pending"] = [task for task in plan["tasks"] if not task["done"]] if plan["current"] else []
    week = collect_week(root, today)
    reviews = collect_review_groups(root, today, cards, archive.get("focus_problems", []))
    log = next((entry for entry in logs if entry["date"] == today), None)
    warnings = []
    if plan["date"] and not plan["current"]:
        warnings.append(f"现有今日计划日期为 {plan['date']}，请先重新安排今天。")
    updated = archive.get("latest_archive_update", "-")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", updated) and updated < (today - timedelta(days=7)).isoformat():
        warnings.append(f"档案更新于 {updated}；其中的聚焦问题可能已过时。")
    return {
        "plan": plan, "week": week, "reviews": reviews,
        "knowledge": collect_knowledge(root, cards), "warnings": warnings,
        "archive_link": make_link(root / "我的学习者档案.md", root),
        "closing": {
            "log_link": make_link(log["path"] if log else log_path_for(root, today), root),
            "hours": log["hours"] if log else None,
            "new_cards": sum(card["created_at"] == today.isoformat() for card in cards),
            "reviewed_cards": sum(card["last_review_at"] == today.isoformat() and card["created_at"] != today.isoformat() for card in cards),
        },
    }
