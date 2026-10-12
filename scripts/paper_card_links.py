"""卷名与卷面题号的确定性关联；不从 qid 或题意猜题号。"""
import re
import unicodedata
from collections import defaultdict
from datetime import date

from archive_ops import extract_heading_block
from card_history import error_events
from study_ops import iter_review_cards
from paper_wrong_questions import _question_limit


ERROR_TYPES = ("没思路", "遗忘", "计算失误", "思路偏差", "时间不够")
SOURCE_NUMBER_RE = re.compile(r"^(.+?)\s*第\s*(\d+)\s*题\s*$")


def paper_key(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value))).strip()


def source_paper(value):
    match = SOURCE_NUMBER_RE.fullmatch(str(value).strip())
    paper = match.group(1).strip() if match else str(value).strip()
    return paper.removesuffix("选填").strip()


def question_number(frontmatter, question=""):
    numbers = set()
    if str(frontmatter.get("question_number", "")).strip():
        raw = str(frontmatter["question_number"]).strip()
        if not re.fullmatch(r"[0-9]+", raw):
            raise ValueError("question_number 必须是正整数")
        numbers.add(int(raw))
    match = SOURCE_NUMBER_RE.fullmatch(str(frontmatter.get("source", "")).strip())
    if match:
        numbers.add(int(match.group(2)))
    # 只读题面/locator 的开头，不把公式数字、年份或选项当题号。
    for text in (question, str(frontmatter.get("locator", ""))):
        first = next((line.strip().removeprefix("- ").strip() for line in text.splitlines() if line.strip()), "")
        match = re.match(r"^(?:第\s*(\d+)\s*题|[（(](\d+)[）)]|(?:题号[：:]\s*)?(\d+)[.．、](?!\d))", first)
        if match:
            # 明确题号存在时，(1)/1. 可能是小问编号，只校验“第N题/题号:N”。
            if numbers and not match.group(1) and not first.startswith("题号"):
                continue
            numbers.add(int(next(group for group in match.groups() if group)))
    if len(numbers) > 1:
        raise ValueError(f"题号信息冲突: {sorted(numbers)}")
    return next(iter(numbers)) if numbers else None


def validate_question_number(subject, number, paper="", paper_type=None, section="整卷"):
    limit = _question_limit(subject, paper, paper_type, section)
    if number < 1 or (limit is not None and number > limit):
        raise ValueError(f"{subject} 题号必须在 1–{limit} 之间" if limit else "题号必须是正整数")


def card_paper_reference(card):
    fm = card["frontmatter"]
    number = question_number(fm, extract_heading_block(card["body"], "题目", 3))
    paper = source_paper(fm.get("paper") or fm.get("source", ""))
    return (paper, number) if paper and number is not None else None


def associate_cards(root, subject, paper, exam_day, paper_type=None, section="整卷"):
    """仅关联同科同卷且该日期有实际错误事件的卡，不修改卡片。"""
    day = date.fromisoformat(exam_day)
    buckets = defaultdict(list)
    warnings = []
    for card in iter_review_cards(root):
        if card["icloud_placeholder"] or card["subject"] != subject:
            continue
        fm = card["frontmatter"]
        source = source_paper(fm.get("paper") or fm.get("source", ""))
        if paper_key(source) != paper_key(source_paper(paper)):
            continue
        if not any(event_day == day for event_day, _ in error_events(card)):
            continue
        try:
            number = question_number(fm, extract_heading_block(card["body"], "题目", 3))
            if number is None:
                raise ValueError("缺少可验证的卷面题号，请归档时传 --question-number 或手动覆盖")
            validate_question_number(subject, number, paper, paper_type, section)
        except ValueError as exc:
            warnings.append({"path": str(card["path"]), "reason": str(exc)})
            continue
        reason = (extract_heading_block(card["body"], "错误原因", 3)
                  or extract_heading_block(card["body"], "错因定位", 3)
                  or str(fm.get("error_type") or "已归档错题"))
        buckets[number].append({
            "question_number": number, "error_description": reason.strip(), "record_date": exam_day,
            "topic": str(fm.get("topic") or "").strip(), "chapter_id": str(fm.get("chapter_id") or ""),
            "question_id": str(fm.get("question_id") or ""), "card_path": str(card["path"]),
            "error_type": str(fm.get("error_type") or ""),
        })
    questions = []
    for number, entries in sorted(buckets.items()):
        qids = {entry["question_id"] or entry["card_path"] for entry in entries}
        if len(qids) > 1:
            warnings.append({"question_number": number, "reason": "同题号匹配多张卡，请手动消歧"})
            continue
        questions.append(entries[0])
    return questions, warnings
