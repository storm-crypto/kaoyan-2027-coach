#!/usr/bin/env python3
"""统计近期同考点错题；仅提供证据，不创建突破单。"""
import argparse
import json
from collections import defaultdict
from datetime import date, timedelta

from card_history import consecutive_failures, error_events, first_wrong_day, history_entries
from paper_card_links import card_paper_reference, paper_key, source_paper
from paper_analysis_lib import module_scores
from env_util import json_error, resolve_obsidian_root
from paper_wrong_questions import query_wrong_questions
from score_record_lib import collect_score_records
from study_ops import iter_review_cards, parse_today


def structured_topic(fields):
    chapter_id = str(fields.get("chapter_id") or "").strip()
    topic = str(fields.get("topic") or "").strip()
    if not chapter_id and not topic:
        return None
    return {"key": ("chapter_id", chapter_id) if chapter_id else ("topic", topic),
            "topic": topic or str(fields.get("chapter_display") or chapter_id).strip(),
            "chapter_id": chapter_id}


def check_triggers(root, today, days=3):
    if days < 1:
        raise ValueError("days 必须大于 0")
    start = today - timedelta(days=days - 1)
    records = collect_score_records(root, section=None)
    questions = query_wrong_questions(records, start_date=start, end_date=today)
    cards = [card for card in iter_review_cards(root) if not card["icloud_placeholder"]]
    by_qid = {str(card["frontmatter"].get("question_id")): card for card in cards if card["frontmatter"].get("question_id")}
    events = {}
    paper_keys = defaultdict(list)
    unmapped = []

    def add_event(key, metadata, source):
        event = events.setdefault(key, {"metadata": metadata, "source": source})
        if metadata and (not event["metadata"] or metadata["chapter_id"]):
            event["metadata"] = metadata

    for question in questions:
        subject, day = question["subject"], date.fromisoformat(question["record_date"])
        number, paper = question["question_number"], question["paper"]
        # 同卷同日的整卷/选填摘要是同一道错题的两种归档范围，不重复计数。
        canonical_paper = paper_key(source_paper(paper))
        key = (subject, day, question['paper_type'], canonical_paper, number)
        reference_key = (subject, day, canonical_paper, number)
        if key not in paper_keys[reference_key]:
            paper_keys[reference_key].append(key)
        source = f"{paper}第{number}题"
        linked = by_qid.get(question.get("question_id"))
        fields = linked["frontmatter"] if linked and linked["subject"] == subject else question
        add_event(key, structured_topic(fields), source)

    for card in cards:
        subject = card["subject"]
        try:
            reference = card_paper_reference(card)
        except ValueError:
            reference = None
        qid = card["frontmatter"].get("question_id") or str(card["path"])
        linked_days = set()
        for day, marker in error_events(card):
            if not start <= day <= today:
                continue
            matches = paper_keys.get((subject, day, paper_key(reference[0]), reference[1]), []) if reference else []
            if len(matches) == 1 and day not in linked_days:
                key = matches[0]
                linked_days.add(day)
            else:
                key = (subject, day, qid, marker)
            add_event(key, structured_topic(card["frontmatter"]), str(qid))

    buckets = {}
    for key, event in events.items():
        metadata = event["metadata"]
        if not metadata:
            unmapped.append({"source": event["source"], "subject": key[0], "record_date": key[1].isoformat()})
            continue
        bucket = buckets.setdefault((key[0], metadata["key"]), {"metadata": metadata, "sources": []})
        bucket["sources"].append(event["source"])
    triggered = []
    for (subject, _), bucket in sorted(buckets.items()):
        if len(bucket["sources"]) < 3:
            continue
        metadata = bucket["metadata"]
        entry = {"topic": metadata["topic"], "count": len(bucket["sources"]),
                 "sources": bucket["sources"], "subject": subject}
        if metadata["chapter_id"]:
            entry["chapter_id"] = metadata["chapter_id"]
        triggered.append(entry)

    result = {"triggered": triggered}
    signals = []
    for card in cards:
        first = first_wrong_day(card)
        if first and first > today:
            continue
        # 不能把历史回放窗口之后发生的翻车当成今天的信号。
        entries = history_entries(card['body'])
        last_review = str(card['frontmatter'].get('last_review_at') or '')
        if (last_review and last_review > today.isoformat()) or any(entry['date'] > today for entry in entries):
            continue
        streak = consecutive_failures(card['frontmatter'], card['body'])
        if streak >= 3:
            signals.append({"reason": "consecutive_failures", "subject": card['subject'],
                            "question_id": str(card['frontmatter'].get('question_id') or ''),
                            "topic": str(card['frontmatter'].get('topic') or ''),
                            "chapter_id": str(card['frontmatter'].get('chapter_id') or ''),
                            "consecutive_failures": streak, "card_path": str(card['path'])})
    for record in records:
        day = date.fromisoformat(record['exam_date'])
        if not start <= day <= today:
            continue
        for module, metrics in module_scores(record).items():
            if 'accuracy' in metrics and metrics['accuracy'] < 0.6:
                signals.append({"reason": "module_accuracy", "subject": record['subject'],
                                "module": module, "accuracy": metrics['accuracy'],
                                "score": metrics['score'], "max_score": metrics['max_score'],
                                "paper": record['paper'], "date": record['exam_date'],
                                "section": record.get('section', '整卷')})
    if signals:
        result['strong_signals'] = signals
    if unmapped:
        result["unmapped"] = unmapped
    return result


def main():
    parser = argparse.ArgumentParser(description="统计同考点近期错误触发证据")
    parser.add_argument("obsidian_root", nargs="?")
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--today", help="统计窗口截止日期 YYYY-MM-DD，默认今天")
    args = parser.parse_args()
    try:
        result = check_triggers(resolve_obsidian_root(args.obsidian_root), parse_today(args.today), args.days)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        json_error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
