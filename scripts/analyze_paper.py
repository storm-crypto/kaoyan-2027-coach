#!/usr/bin/env python3
"""整卷纵向序列：总分、模块分/得分率与各 topic 错题数；只读。"""
import argparse
import json
from collections import Counter
from datetime import date

from env_util import json_error, resolve_obsidian_root
from paper_analysis_lib import module_scores
from paper_card_links import associate_cards, paper_key
from score_record_lib import collect_score_records, normalize_subject
from paper_wrong_questions import _question_limit


def analyze_papers(root, subject, papers=None, start_date=None, end_date=None, section='整卷'):
    _question_limit(subject, '', '真题', section)
    if start_date and end_date and start_date > end_date:
        raise ValueError("start-date 不能晚于 end-date")
    paper_names = {paper_key(paper) for paper in papers or []}
    sequence = []
    all_topics = set()
    warnings = []
    for record in collect_score_records(root, [subject], section=section):
        day = date.fromisoformat(record["exam_date"])
        if paper_names and paper_key(record["paper"]) not in paper_names:
            continue
        if start_date and day < start_date or end_date and day > end_date:
            continue
        questions = record["wrong_questions"]
        if not questions and record['wrong_questions_mode'] != 'manual':
            questions, link_warnings = associate_cards(root, subject, record["paper"], record["exam_date"], record["paper_type"], section)
            warnings.extend(link_warnings)
        counts = Counter()
        seen = set()
        for question in questions:
            topic = str(question.get("topic") or "").strip()
            key = (question["question_number"], topic)
            if topic and key not in seen:
                counts[topic] += 1
                seen.add(key)
            elif not topic:
                warnings.append({"paper": record["paper"], "question_number": question["question_number"],
                                 "reason": "缺少结构化 topic，未计入考点序列"})
        all_topics.update(counts)
        sequence.append({"date": record["exam_date"], "paper": record["paper"], "paper_type": record["paper_type"],
                         "total_score": record["total_score"], "modules": module_scores(record),
                         "topic_wrong_counts": dict(sorted(counts.items())), "record_path": record["path"]})
    series = [{"topic": topic, "sequence": [
        {"date": record["date"], "paper": record["paper"], "paper_type": record["paper_type"],
         "wrong_count": record["topic_wrong_counts"].get(topic, 0)} for record in sequence
    ]} for topic in sorted(all_topics)]
    result = {"subject": subject, "section": section, "papers": sequence, "topic_wrong_count_series": series,
              "count_basis": "已记录或已归档的卷面错题；未记录的错误不能推断"}
    if warnings:
        result["warnings"] = warnings
    return result


def main():
    parser = argparse.ArgumentParser(description="输出整卷全序列数据，不做趋势解读")
    parser.add_argument("obsidian_root", nargs="?")
    parser.add_argument("--subject", required=True)
    parser.add_argument('--section', choices=['整卷', '选填'], default='整卷')
    parser.add_argument("--paper", action="append", help="精确卷名，可重复；省略读取该科全部记录")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    args = parser.parse_args()
    try:
        result = analyze_papers(resolve_obsidian_root(args.obsidian_root), normalize_subject(args.subject), args.paper,
                                date.fromisoformat(args.start_date) if args.start_date else None,
                                date.fromisoformat(args.end_date) if args.end_date else None, args.section)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        json_error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
