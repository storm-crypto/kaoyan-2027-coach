"""学习流程共享工具：日期、时长、科目顺序、到期错题扫描。"""
from datetime import date
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple, TypedDict

from constants import PLAN_SUBJECTS, SCORE_SUBJECTS, SRS_GRADUATED_INTERVAL_DAYS
from env_util import is_icloud_placeholder, safe_int
from frontmatter import Frontmatter, parse_frontmatter


class ReviewCard(TypedDict):
    path: Path
    subject: str
    topic: str
    frontmatter: Frontmatter
    body: str
    key_order: List[str]
    next_review: Optional[date]
    review_interval: Optional[int]
    icloud_placeholder: bool


class DueCard(TypedDict):
    path: str
    subject: str
    topic: str
    review_interval: int
    frontmatter: Frontmatter
    body: str
    key_order: List[str]
    filename: str


def parse_today(value: Optional[str]) -> date:
    return date.fromisoformat(value) if value else date.today()


def format_hours(value: float) -> str:
    rounded = round(value * 2) / 2
    if abs(rounded - int(rounded)) < 1e-9:
        return str(int(rounded))
    return f"{rounded:.1f}"


def iter_review_cards(obsidian_root: Path) -> Iterator[ReviewCard]:
    root = Path(obsidian_root) / "错题本"
    if not root.exists():
        return

    for md_file in sorted(root.rglob("*.md")):
        if is_icloud_placeholder(md_file):
            yield {
                "path": md_file,
                "subject": "",
                "topic": md_file.stem,
                "frontmatter": {},
                "body": "",
                "key_order": [],
                "next_review": None,
                "review_interval": None,
                "icloud_placeholder": True,
            }
            continue

        try:
            text = md_file.read_text(encoding="utf-8")
            fm, body, key_order = parse_frontmatter(text)
        except (OSError, UnicodeDecodeError):
            continue

        next_review: Optional[date] = None
        if "next_review" in fm:
            try:
                next_review = date.fromisoformat(str(fm["next_review"]))
            except (TypeError, ValueError):
                next_review = None

        rel = md_file.relative_to(root)
        yield {
            "path": md_file,
            "subject": rel.parts[0] if rel.parts else "未知",
            "topic": fm.get("topic", md_file.stem),
            "frontmatter": fm,
            "body": body,
            "key_order": key_order,
            "next_review": next_review,
            "review_interval": safe_int(fm.get("review_interval", 1)),
            "icloud_placeholder": False,
        }


def collect_due_cards(obsidian_root: Path, today: date) -> List[DueCard]:
    due_cards: List[DueCard] = []
    for item in iter_review_cards(obsidian_root):
        if item["icloud_placeholder"] or item["next_review"] is None or item["review_interval"] is None:
            continue
        if item["next_review"] <= today and item["review_interval"] < SRS_GRADUATED_INTERVAL_DAYS:
            due_cards.append({
                "path": str(item["path"]),
                "subject": item["subject"],
                "topic": item["topic"],
                "review_interval": item["review_interval"],
                "frontmatter": item["frontmatter"],
                "body": item["body"],
                "key_order": item["key_order"],
                "filename": item["path"].stem,
            })
    return sorted(due_cards, key=lambda item: (item["review_interval"], item["subject"], item["topic"]))


def count_due_reviews(obsidian_root: Path, today: date, subjects: Sequence[str]) -> Tuple[int, Dict[str, int]]:
    due_counts = {subject: 0 for subject in subjects}
    due_total = 0
    for item in collect_due_cards(obsidian_root, today):
        due_total += 1
        if item["subject"] in due_counts:
            due_counts[item["subject"]] += 1
    return due_total, due_counts
