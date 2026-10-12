#!/usr/bin/env python3
"""统计近期同考点错题；仅提供证据，不创建突破单。"""
import argparse
import json
import re
from collections import defaultdict
from datetime import date, timedelta

from archive_ops import extract_heading_block
from env_util import json_error, resolve_obsidian_root
from paper_wrong_questions import query_wrong_questions
from score_record_lib import collect_score_records
from study_ops import iter_review_cards, parse_today


def normalize_topic(value):
    value = re.sub(r"^#?(?:topic|chapter)/", "", str(value).strip())
    return re.sub(r"^\d+(?:\.\d+)*\s+", "", value).strip()


def card_topics(card):
    fm = card["frontmatter"]
    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    topic_tags = [tag for tag in tags if str(tag).lstrip("#").startswith("topic/")]
    chapter_tags = [tag for tag in tags if str(tag).lstrip("#").startswith("chapter/")]
    values = fm.get("topic") or topic_tags or re.findall(r"(?<!\S)#topic/([^\s#]+)", card["body"])
    if not values:
        values = fm.get("chapter_display") or fm.get("chapter") or chapter_tags or re.findall(
            r"(?<!\S)#chapter/([^\s#]+)", card["body"])
    if isinstance(values, str):
        values = [values]
    return {normalize_topic(value) for value in values or [] if normalize_topic(value)}


def topic_vocabulary(root, cards, questions):
    vocabulary = defaultdict(set)
    for card in cards:
        vocabulary[card["subject"]].update(card_topics(card))
    for question in questions:
        if question.get("topic"):
            vocabulary[question["subject"]].add(normalize_topic(question["topic"]))
    map_root = root / "知识地图"
    for path in sorted(map_root.glob("*.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.lstrip().startswith("|"):
                continue
            keyword = normalize_topic(line.split("|")[1].strip().strip("*"))
            if keyword and keyword != "考点" and not re.fullmatch(r"[- :]+", keyword):
                vocabulary[path.stem].add(keyword)
    return vocabulary


def matching_topics(description, vocabulary):
    text = re.sub(r"\s+", "", description).casefold()
    matches = set()
    for topic in vocabulary:
        keyword = re.sub(r"\s+", "", topic).casefold()
        pattern = re.escape(keyword)
        if keyword.isascii():
            pattern = rf"(?<![a-z0-9]){pattern}(?![a-z0-9])"
        if re.search(pattern, text):
            matches.add(topic)
    # 同一次错误只落入最具体的关键词，避免同时触发其上位词。
    return {topic for topic in matches if not any(
        topic != other and topic.casefold() in other.casefold() for other in matches)}


def wrong_events(card):
    fm = card["frontmatter"]
    first_day = None
    first = fm.get("first_wrong_at")
    if first:
        try:
            first_day = date.fromisoformat(str(first))
        except ValueError:
            pass
    events = [(first_day, "first")] if first_day else []
    seen = set()
    initial_history_seen = False
    history = extract_heading_block(card["body"], "历史记录", level=3)
    for line in history.splitlines():
        match = re.match(r"^-\s*(\d{4}-\d{2}-\d{2})\s*-\s*(不会|半会|会)\s*-", line.strip())
        if not match or line.strip() in seen:
            continue
        seen.add(line.strip())
        try:
            day = date.fromisoformat(match.group(1))
        except ValueError:
            continue
        # 首次归档已由 first_wrong_at 表示，不能重复计入；之后真实重错仍计数。
        if day == first_day and not initial_history_seen:
            initial_history_seen = True
            continue
        if match.group(2) != "会":
            events.append((day, line.strip()))
    return sorted(events)  # 完全相同的历史行去重，不使用累计 wrong_count。


def card_paper_reference(card):
    fm = card["frontmatter"]
    if fm.get("paper") and str(fm.get("question_number", "")).isdigit():
        return str(fm["paper"]).strip(), int(fm["question_number"])
    # 只有来源明确含卷面题号时才关联，不能按关键词猜同一题。
    match = re.fullmatch(r"(.+?)\s*第\s*(\d+)\s*题", str(fm.get("source", "")).strip())
    return (match.group(1).strip(), int(match.group(2))) if match else None


def check_triggers(root, today, days=3):
    if days < 1:
        raise ValueError("days 必须大于 0")
    start = today - timedelta(days=days - 1)
    questions = query_wrong_questions(collect_score_records(root), start_date=start, end_date=today)
    cards = [card for card in iter_review_cards(root) if not card["icloud_placeholder"]]
    vocabulary = topic_vocabulary(root, cards, questions)
    events = {}
    paper_keys = defaultdict(list)
    unmapped = []

    def add_event(key, topics, source):
        event = events.setdefault(key, {"topics": set(), "source": source})
        event["topics"].update(topics)

    for question in questions:
        subject, day = question["subject"], date.fromisoformat(question["record_date"])
        number, paper = question["question_number"], question["paper"]
        key = (subject, day, question["path"], number)
        paper_keys[(subject, day, paper, number)].append(key)
        source = f"{paper}第{number}题"
        topics = ({normalize_topic(question["topic"])} if question.get("topic") else
                  matching_topics(question["error_description"], vocabulary[subject]))
        add_event(key, topics, source)

    for card in cards:
        subject = card["subject"]
        reference = card_paper_reference(card)
        qid = card["frontmatter"].get("question_id") or str(card["path"])
        linked_days = set()
        for day, marker in wrong_events(card):
            if not start <= day <= today:
                continue
            matches = paper_keys.get((subject, day, *reference), []) if reference else []
            if len(matches) == 1 and day not in linked_days:
                key = matches[0]
                linked_days.add(day)
            else:
                key = (subject, day, qid, marker)
            add_event(key, card_topics(card), str(qid))

    buckets = defaultdict(list)
    for key, event in events.items():
        if not event["topics"]:
            unmapped.append({"source": event["source"], "subject": key[0], "record_date": key[1].isoformat()})
        for topic in sorted(event["topics"]):
            buckets[(key[0], topic)].append(event["source"])
    triggered = [
        {"topic": topic, "count": len(sources), "sources": sources, "subject": subject}
        for (subject, topic), sources in sorted(buckets.items()) if len(sources) >= 3
    ]
    result = {"triggered": triggered}
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
