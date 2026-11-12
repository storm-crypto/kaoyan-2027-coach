#!/usr/bin/env python3
"""生成单套试卷（或数学选填专项）的深度复盘报告，并写入 复盘报告/。

核心功能：
1. 聚合本卷成绩（支持读取已有 /score 记录，或在调用时通过 --total 等参数同步写入成绩记录）
2. 自动关联并深度读取本卷已归档的 /wrong 错题卡（章节、考点、错因、复盘口诀、元技能簇），并与 /score 轻量记录的粗心题合并
3. 拆解卷面基本盘（模块得分率、数学高数/线代/概率及 408 四科题号映射、稳固阵地与历史止血信号）
4. 核算失分账本（硬伤失分 vs 方法失分 vs 冤枉失分、客观题确定性冤枉分与保底潜力分）
5. 穿透历史数据（判定每道错题是跨卷/历史惯犯还是新暴露初犯，直链同簇兄弟卡与突破单触发信号）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from archive_ops import (
    extract_heading_block,
    format_number,
    load_archive_text,
    load_template_markdown,
    parse_subject_targets,
    update_archive_date,
    upsert_math_objective_score_row,
    upsert_subject_score_row,
)
from breakthrough_ops import parse_breakthroughs
from card_progress import LIGHTS, card_progress
from check_breakthrough_triggers import check_triggers
from cs_card_layout import DIAGNOSIS, extract_module, unfold_callout
from env_util import atomic_write, json_error, resolve_obsidian_root
from find_related_cards import load_index
from paper_analysis_lib import FOUR_OH_EIGHT_MAX, module_scores
from scan_due_reviews import build_question_payload
from paper_card_links import (
    ERROR_TYPES,
    associate_cards,
    paper_key,
    question_number as extract_card_question_number,
    source_paper,
    validate_question_number,
)
from paper_wrong_questions import (
    _question_limit,
    build_wrong_questions,
    is_old_math_paper,
    objective_max_score,
)
from record_paper_score import LOSS_FIELDS_BY_SUBJECT, _all_extra_fields, _field_to_cli
from score_record_lib import (
    SUBJECT_ALIASES,
    SUBJECT_SCORE_FIELDS,
    SUBJECT_TOTALS,
    build_summary_row_from_record,
    collect_score_records,
    infer_paper_type,
    normalize_subject,
    parse_non_negative_number,
    parse_score_record,
    sanitize_filename_segment,
    validate_score_breakdown,
    write_score_record,
)
from study_ops import iter_review_cards
from today_wrong_ops import PLACEHOLDER_TOKEN, _infer_chapter, extract_takeaway


ERROR_TYPE_KEYWORDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("计算失误", ("计算失误", "算错", "粗心", "抄错", "符号错", "看错", "漏写", "笔误", "计算错误", "口算")),
    ("时间不够", ("时间不够", "没时间", "来不及", "没做完", "超时", "时间紧")),
    ("遗忘", ("遗忘", "忘了", "忘记", "记错", "没记住", "公式不熟", "概念模糊")),
    ("思路偏差", ("思路偏差", "想偏", "走弯路", "方法错", "方向错", "漏条件", "套错", "误判")),
    ("没思路", ("没思路", "不会", "无思路", "不知如何下手", "下不了手", "卡死", "完全不会", "卡住")),
)

LOSS_BUCKET_SPECS: Tuple[Tuple[str, str, Tuple[str, ...], str], ...] = (
    ("hard_gap", "硬伤失分（知识与概念盲区）", ("没思路", "遗忘"), "概念/定理生疏或题型完全陌生，需回归讲义与错题卡补课"),
    ("method_gap", "方法失分（破题与路径偏差）", ("思路偏差",), "看到条件未能触发正确第一步，需強化元技能触发信号"),
    ("regrettable", "冤枉失分（计算与时间策略）", ("计算失误", "时间不够"), "会做但算错/超时，属于考场最易追回的直接提分空间"),
    ("unclassified", "待归因失分", ("待归因",), "尚未标注具体错因，建议补充 --error-type"),
)

MATH1_SUBSUBJECT_LABELS = {
    "gaoshu": "高等数学",
    "linear": "线性代数",
    "probability": "概率论与数理统计",
}

FOUR_OH_EIGHT_LABELS = {
    "DS": "数据结构",
    "CO": "计算机组成原理",
    "OS": "操作系统",
    "CN": "计算机网络",
}


def resolve_error_type(raw_error_type: str, description: str = "") -> str:
    raw = str(raw_error_type or "").strip()
    if raw in ERROR_TYPES:
        return raw
    combined = f"{raw} {description}".strip()
    for canonical, keywords in ERROR_TYPE_KEYWORDS:
        if any(keyword in combined for keyword in keywords):
            return canonical
    return "待归因"


def error_bucket_key(error_type: str) -> str:
    for key, _label, types, _desc in LOSS_BUCKET_SPECS:
        if error_type in types:
            return key
    return "unclassified"


def classify_question_slot(
    subject: str,
    number: int,
    paper: str,
    paper_type: str,
    chapter_id: str = "",
) -> Dict[str, object]:
    """根据科目、题号与 chapter_id 推断所属子科目、题型与客观题确定性分值。"""
    cid = str(chapter_id or "").strip().lower()
    if subject == "数学一":
        old_format = is_old_math_paper(paper, paper_type)
        if old_format:
            if 1 <= number <= 8:
                q_type, is_obj, pts = "选择题", True, 4.0
                default_sub = "高等数学" if number <= 4 else ("线性代数" if number <= 6 else "概率论与数理统计")
            elif 9 <= number <= 14:
                q_type, is_obj, pts = "填空题", True, 4.0
                default_sub = "高等数学" if number <= 12 else ("线性代数" if number == 13 else "概率论与数理统计")
            else:
                q_type, is_obj, pts = "解答题", False, 10.0 if number <= 19 else 11.0
                default_sub = "高等数学" if number <= 19 else ("线性代数" if number <= 21 else "概率论与数理统计")
        else:
            if 1 <= number <= 10:
                q_type, is_obj, pts = "选择题", True, 5.0
                default_sub = "高等数学" if number <= 4 else ("线性代数" if number <= 7 else "概率论与数理统计")
            elif 11 <= number <= 16:
                q_type, is_obj, pts = "填空题", True, 5.0
                default_sub = "高等数学" if number <= 14 else ("线性代数" if number == 15 else "概率论与数理统计")
            else:
                q_type, is_obj, pts = "解答题", False, 10.0 if number == 17 else 12.0
                default_sub = "高等数学" if number <= 20 else ("线性代数" if number == 21 else "概率论与数理统计")

        subsubject = default_sub
        for slug, label in MATH1_SUBSUBJECT_LABELS.items():
            if cid.startswith(f"math1:{slug}"):
                subsubject = label
                break
        return {
            "subsubject": subsubject,
            "question_type": q_type,
            "is_objective": is_obj,
            "objective_points": pts if is_obj else 0.0,
            "nominal_points": pts,
        }

    if subject == "408":
        if 1 <= number <= 40:
            q_type, is_obj, pts = "选择题", True, 2.0
            if number <= 11:
                code = "DS"
            elif number <= 22:
                code = "CO"
            elif number <= 32:
                code = "OS"
            else:
                code = "CN"
        else:
            q_type, is_obj, pts = "综合应用题", False, 0.0
            if number <= 42:
                code = "DS"
            elif number <= 44:
                code = "CO"
            elif number <= 46:
                code = "OS"
            else:
                code = "CN"
        for slug, mod_code in (("ds", "DS"), ("co", "CO"), ("os", "OS"), ("cn", "CN")):
            if cid.startswith(f"408:{slug}"):
                code = mod_code
                break
        return {
            "subsubject": f"{code}（{FOUR_OH_EIGHT_LABELS[code]}）",
            "subsubject_code": code,
            "question_type": q_type,
            "is_objective": is_obj,
            "objective_points": pts if is_obj else 0.0,
            "nominal_points": pts,
        }

    return {
        "subsubject": subject,
        "question_type": "题目",
        "is_objective": False,
        "objective_points": 0.0,
        "nominal_points": 0.0,
    }


def extract_full_action_hook(body: str, subject: str) -> str:
    """提取错题卡中的考场复盘口诀（数学保留完整『看到→先做→再做』链，408保留口令与核心规则）。"""
    if subject == "数学一":
        block = extract_heading_block(body, "下次怎么做", level=3)
        bullets = [
            line.strip()[2:].strip()
            for line in block.splitlines()
            if line.strip().startswith("- ")
            and line.strip()[2:].strip()
            and PLACEHOLDER_TOKEN not in line
        ]
        if bullets:
            return " → ".join(bullets)
    if subject == "408":
        takeaway = extract_takeaway(body, "408")
        if takeaway:
            return takeaway
    return extract_takeaway(body, subject)


def extract_mistake_summary(body: str, subject: str, fallback: str = "") -> str:
    """提取错题卡里的精炼错因描述。"""
    if subject == "408":
        diag = unfold_callout(extract_module(body, DIAGNOSIS) or "")
        for line in diag.splitlines():
            stripped = line.strip().removeprefix("- ").strip()
            if stripped.startswith(("实际错误", "错因", "核心错因", "根因")):
                return stripped
    for heading in ("错因定位", "错误原因"):
        block = extract_heading_block(body, heading, level=3)
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                val = stripped[2:].strip()
                if val and PLACEHOLDER_TOKEN not in val:
                    return val
    return fallback.strip()


def build_report_path(
    obsidian_root: Path,
    exam_day: str,
    subject: str,
    paper: str,
    section: str = "整卷",
) -> Path:
    sec_part = "-选填" if section == "选填" else ""
    filename = (
        f"{exam_day}-{sanitize_filename_segment(subject)}{sec_part}"
        f"-{sanitize_filename_segment(paper)}-套卷分析.md"
    )
    return Path(obsidian_root) / "复盘报告" / filename


def _find_matching_cards_across_days(
    obsidian_root: Path,
    subject: str,
    paper: str,
    paper_type: str,
    section: str,
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    """扫描全库属于同科、同卷名的错题卡（支持隔天补录的 /wrong 错题卡）。"""
    target_key = paper_key(source_paper(paper))
    buckets: Dict[int, List[Dict[str, object]]] = defaultdict(list)
    warnings: List[Dict[str, object]] = []
    for card in iter_review_cards(obsidian_root):
        if card["icloud_placeholder"] or card["subject"] != subject:
            continue
        fm = card["frontmatter"]
        source = source_paper(fm.get("paper") or fm.get("source", ""))
        if paper_key(source) != target_key:
            continue
        try:
            number = extract_card_question_number(fm, extract_heading_block(card["body"], "题目", 3))
            if number is None:
                continue
            validate_question_number(subject, number, paper, paper_type, section)
        except ValueError as exc:
            warnings.append({"path": str(card["path"]), "reason": str(exc)})
            continue
        reason = (
            extract_heading_block(card["body"], "错误原因", 3)
            or extract_heading_block(card["body"], "错因定位", 3)
            or str(fm.get("error_type") or "已归档错题")
        )
        buckets[number].append({
            "question_number": number,
            "error_description": reason.strip(),
            "record_date": str(fm.get("first_wrong_at") or ""),
            "topic": str(fm.get("topic") or "").strip(),
            "chapter_id": str(fm.get("chapter_id") or "").strip(),
            "question_id": str(fm.get("question_id") or "").strip(),
            "card_path": str(card["path"]),
            "error_type": str(fm.get("error_type") or "").strip(),
        })
    results: List[Dict[str, object]] = []
    for number, entries in sorted(buckets.items()):
        qids = {entry["question_id"] or entry["card_path"] for entry in entries}
        if len(qids) > 1:
            continue
        results.append(entries[0])
    return results, warnings


def collect_merged_wrong_questions(
    obsidian_root: Path,
    record: Mapping[str, object],
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    """合并成绩单中的轻量错题记录与错题本中的 /wrong 卡片详情。"""
    subject = str(record["subject"])
    paper = str(record["paper"])
    paper_type = str(record["paper_type"])
    exam_date = str(record["exam_date"])
    section = str(record.get("section") or "整卷")

    stored_questions = list(record.get("wrong_questions") or [])
    mode = str(record.get("wrong_questions_mode") or "")

    # 若用户显式传了 --wrong-questions "" 清空，且无任何已保存项，则尊重清空
    if mode == "manual" and not stored_questions:
        return [], []

    same_day_cards, warnings = associate_cards(
        obsidian_root, subject, paper, exam_date, paper_type, section
    )
    all_day_cards, extra_warnings = _find_matching_cards_across_days(
        obsidian_root, subject, paper, paper_type, section
    )
    for w in extra_warnings:
        if w not in warnings:
            warnings.append(w)

    by_number: Dict[int, Dict[str, object]] = {}
    for entry in all_day_cards:
        by_number[int(entry["question_number"])] = dict(entry)
    for entry in same_day_cards:
        by_number[int(entry["question_number"])] = dict(entry)

    for manual in stored_questions:
        num = int(manual["question_number"])
        if num in by_number:
            merged = dict(by_number[num])
            # 保留成绩记录里手动填写的错因描述或补充 topic
            if manual.get("topic") and not merged.get("topic"):
                merged["topic"] = manual["topic"]
            if manual.get("error_type") and not merged.get("error_type"):
                merged["error_type"] = manual["error_type"]
            if manual.get("error_description") and mode == "manual":
                merged["manual_description"] = str(manual["error_description"])
            by_number[num] = merged
        else:
            by_number[num] = dict(manual)

    return [by_number[num] for num in sorted(by_number)], warnings


def enrich_wrong_questions(
    obsidian_root: Path,
    record: Mapping[str, object],
    raw_questions: Sequence[Mapping[str, object]],
    all_cards: Sequence[Mapping[str, object]],
    all_records: Sequence[Mapping[str, object]],
) -> List[Dict[str, object]]:
    """为每道错题注入卡片正文细节、元技能簇、分科题型以及历史惯犯/初犯穿透信息。"""
    subject = str(record["subject"])
    paper = str(record["paper"])
    paper_type = str(record["paper_type"])
    exam_date = str(record["exam_date"])
    current_paper_key = paper_key(source_paper(paper))

    cards_by_path = {str(c["path"]): c for c in all_cards}
    cards_by_qid = {
        str(c["frontmatter"].get("question_id") or ""): c
        for c in all_cards
        if c["frontmatter"].get("question_id")
    }

    # 元技能簇映射
    index_data = load_index(Path(obsidian_root))
    qid_to_cluster: Dict[str, Dict[str, object]] = {}
    for cluster in index_data.get("clusters", []):
        for q in cluster.get("qids", []) + cluster.get("also", []):
            norm_q = str(q).removeprefix("qid-")
            qid_to_cluster.setdefault(norm_q, cluster)

    enriched: List[Dict[str, object]] = []
    for item in raw_questions:
        num = int(item["question_number"])
        qid = str(item.get("question_id") or "").strip()
        card_path_str = str(item.get("card_path") or "").strip()
        card = cards_by_qid.get(qid) or cards_by_path.get(card_path_str)

        fm = card["frontmatter"] if card else {}
        body = card["body"] if card else ""
        has_card = card is not None

        topic = str(item.get("topic") or fm.get("topic") or "").strip()
        chapter_id = str(item.get("chapter_id") or fm.get("chapter_id") or "").strip()
        chapter_display = str(fm.get("chapter_display") or "").strip()
        if not chapter_display and card is not None:
            chapter_display = _infer_chapter(Path(card["path"]), Path(obsidian_root))

        raw_err_type = str(item.get("error_type") or fm.get("error_type") or "").strip()
        manual_desc = str(item.get("manual_description") or item.get("error_description") or "").strip()
        mistake_summary = extract_mistake_summary(body, subject, manual_desc) if has_card else manual_desc
        canonical_err_type = resolve_error_type(raw_err_type, f"{manual_desc} {mistake_summary}")
        bucket_key = error_bucket_key(canonical_err_type)

        slot = classify_question_slot(subject, num, paper, paper_type, chapter_id)
        action_hook = extract_full_action_hook(body, subject) if has_card else ""
        card_status = str(fm.get("status") or "不会").strip() if has_card else "未建卡"
        progress_info = card_progress(body) if has_card else None
        q_text, _, q_preview = build_question_payload(body, topic) if has_card else ("", "", "")

        wikilink = ""
        if has_card:
            stem = Path(card["path"]).stem
            label = f"第{num}题：{topic or chapter_display or stem}"
            wikilink = f"[[{stem}|{label}]]"

        # 元技能簇与同簇兄弟卡
        cluster_info = None
        norm_qid = qid.removeprefix("qid-") if qid else ""
        if norm_qid and norm_qid in qid_to_cluster:
            cluster = qid_to_cluster[norm_qid]
            c_id = str(cluster.get("id") or "")
            c_name = str(cluster.get("name") or cluster.get("topic") or c_id)
            siblings: List[str] = []
            for sib_q in cluster.get("qids", []) + cluster.get("also", []):
                norm_sib = str(sib_q).removeprefix("qid-")
                if norm_sib == norm_qid:
                    continue
                sib_card = cards_by_qid.get(f"qid-{norm_sib}") or cards_by_qid.get(norm_sib)
                if sib_card:
                    sib_stem = Path(sib_card["path"]).stem
                    sib_topic = str(sib_card["frontmatter"].get("topic") or sib_stem)
                    siblings.append(f"[[{sib_stem}|{sib_topic}]]")
                if len(siblings) >= 3:
                    break
            cluster_info = {
                "id": c_id,
                "name": c_name,
                "sibling_links": siblings,
            }

        # 历史穿透：统计同 chapter_id（优先）或同 topic 在历史错题卡与前序套卷中的出现次数
        prior_sources: List[str] = []
        seen_source_keys = set()
        if qid:
            seen_source_keys.add(f"qid:{qid}")
        seen_source_keys.add(f"paper:{current_paper_key}:{num}")

        for other_card in all_cards:
            if other_card["subject"] != subject:
                continue
            ofm = other_card["frontmatter"]
            oqid = str(ofm.get("question_id") or "")
            if qid and oqid == qid:
                continue
            first_day = str(ofm.get("first_wrong_at") or "")
            if first_day and first_day > exam_date:
                continue
            o_cid = str(ofm.get("chapter_id") or "").strip()
            o_topic = str(ofm.get("topic") or "").strip()
            matched = False
            if chapter_id and o_cid:
                matched = chapter_id == o_cid
            elif topic and o_topic:
                matched = topic == o_topic
            if not matched:
                continue
            s_key = f"qid:{oqid or other_card['path']}"
            if s_key in seen_source_keys:
                continue
            seen_source_keys.add(s_key)
            ostem = Path(other_card["path"]).stem
            osource = str(ofm.get("source") or "错题本")
            prior_sources.append(f"[[{ostem}|{osource}（{o_topic or chapter_display}）]]")

        for other_rec in all_records:
            if other_rec["subject"] != subject:
                continue
            if str(other_rec["exam_date"]) > exam_date:
                continue
            other_pkey = paper_key(source_paper(str(other_rec["paper"])))
            if other_pkey == current_paper_key and str(other_rec["exam_date"]) == exam_date:
                continue
            for oq in other_rec.get("wrong_questions") or []:
                oqid = str(oq.get("question_id") or "")
                if oqid and f"qid:{oqid}" in seen_source_keys:
                    continue
                o_cid = str(oq.get("chapter_id") or "").strip()
                o_topic = str(oq.get("topic") or "").strip()
                matched = False
                if chapter_id and o_cid:
                    matched = chapter_id == o_cid
                elif topic and o_topic:
                    matched = topic == o_topic
                if not matched:
                    continue
                p_key = f"paper:{other_pkey}:{oq['question_number']}"
                if p_key in seen_source_keys:
                    continue
                seen_source_keys.add(p_key)
                prior_sources.append(f"{other_rec['paper']}第{oq['question_number']}题")

        prior_count = len(prior_sources)
        enriched.append({
            "question_number": num,
            "question_type": slot["question_type"],
            "subsubject": slot["subsubject"],
            "is_objective": slot["is_objective"],
            "objective_points": slot["objective_points"],
            "nominal_points": slot["nominal_points"],
            "topic": topic or "未标注考点",
            "chapter_id": chapter_id,
            "chapter_display": chapter_display or "未映射章节",
            "error_type": canonical_err_type,
            "raw_error_type": raw_err_type,
            "bucket_key": bucket_key,
            "mistake_summary": mistake_summary or canonical_err_type,
            "action_hook": action_hook,
            "has_card": has_card,
            "status": card_status,
            "progress": progress_info,
            "question_text": q_text,
            "question_preview": q_preview,
            "question_id": qid,
            "card_path": card_path_str,
            "wikilink": wikilink,
            "cluster": cluster_info,
            "is_repeat_offender": prior_count >= 1,
            "prior_wrong_count": prior_count,
            "total_occurrences": prior_count + 1,
            "prior_sources": prior_sources[:3],
        })
    return enriched


def build_paper_review_queue(
    enriched_questions: Sequence[Mapping[str, object]],
) -> Tuple[Dict[str, int], List[Dict[str, object]]]:
    """为已复盘过的试卷生成错题二刷队列（按 不会 → 半会 → 会但未三连绿 → 已过关 排序）。"""
    card_items = [q for q in enriched_questions if q["has_card"]]
    passed_count = sum(1 for q in card_items if q.get("progress") and q["progress"].get("passed"))
    mastered_once_count = sum(1 for q in card_items if q.get("status") == "会")
    pending_count = sum(1 for q in card_items if q.get("status") in {"不会", "半会"})

    def _priority(item: Mapping[str, object]) -> Tuple[int, int]:
        prog = item.get("progress") or {}
        if prog.get("passed"):
            rank = 3
        elif item.get("status") == "不会":
            rank = 0
        elif item.get("status") == "半会":
            rank = 1
        else:
            rank = 2
        return (rank, int(item["question_number"]))

    queue = [
        {
            "question_number": q["question_number"],
            "question_id": q["question_id"],
            "card_path": q["card_path"],
            "wikilink": q["wikilink"],
            "subsubject": q["subsubject"],
            "question_type": q["question_type"],
            "topic": q["topic"],
            "chapter_display": q["chapter_display"],
            "error_type": q["error_type"],
            "status": q["status"],
            "progress": q["progress"],
            "question_text": q["question_text"],
            "question_preview": q["question_preview"],
        }
        for q in sorted(card_items, key=_priority)
    ]
    summary = {
        "total_card_count": len(card_items),
        "passed_count": passed_count,
        "mastered_once_count": mastered_once_count,
        "pending_count": pending_count,
    }
    return summary, queue


def build_subsubject_summary(
    subject: str,
    paper: str,
    paper_type: str,
    section: str,
    enriched_questions: Sequence[Mapping[str, object]],
) -> List[Dict[str, object]]:
    """统计各子科目的错题数与客观题推算得分（数学一三科 / 408 四科）。"""
    if subject == "数学一":
        old_format = is_old_math_paper(paper, paper_type)
        specs = (
            ("高等数学", 32.0 if old_format else 40.0),
            ("线性代数", 12.0 if old_format else 20.0),
            ("概率论与数理统计", 12.0 if old_format else 20.0),
        )
        rows = []
        for name, obj_max in specs:
            items = [q for q in enriched_questions if q["subsubject"] == name]
            obj_items = [q for q in items if q["is_objective"]]
            big_items = [q for q in items if not q["is_objective"]]
            obj_lost = sum(float(q["objective_points"]) for q in obj_items)
            obj_est = max(0.0, obj_max - obj_lost)
            rows.append({
                "subsubject": name,
                "objective_max": obj_max,
                "objective_estimated_score": obj_est,
                "objective_accuracy": obj_est / obj_max if obj_max else None,
                "objective_wrong_count": len(obj_items),
                "big_wrong_count": len(big_items) if section != "选填" else 0,
                "total_wrong_count": len(items),
                "question_numbers": [int(q["question_number"]) for q in items],
            })
        return rows

    if subject == "408":
        specs = (
            ("DS", "DS（数据结构）", 22.0),
            ("CO", "CO（计算机组成原理）", 22.0),
            ("OS", "OS（操作系统）", 20.0),
            ("CN", "CN（计算机网络）", 16.0),
        )
        rows = []
        for code, label, obj_max in specs:
            items = [q for q in enriched_questions if q.get("subsubject") == label]
            obj_items = [q for q in items if q["is_objective"]]
            big_items = [q for q in items if not q["is_objective"]]
            rows.append({
                "subsubject": label,
                "code": code,
                "objective_max": obj_max,
                "objective_wrong_count": len(obj_items),
                "big_wrong_count": len(big_items),
                "total_wrong_count": len(items),
                "question_numbers": [int(q["question_number"]) for q in items],
            })
        return rows

    return []


def build_strengths_and_stopped_bleeding(
    record: Mapping[str, object],
    modules: Mapping[str, Mapping[str, object]],
    subsubject_rows: Sequence[Mapping[str, object]],
    enriched_questions: Sequence[Mapping[str, object]],
    prior_records: Sequence[Mapping[str, object]],
    archive_text: str,
) -> Tuple[List[str], List[str]]:
    """提取真实有数据支撑的『稳固阵地』与『阶段止血信号』，绝不凭空脑补未测考点。"""
    strengths: List[str] = []
    stopped_bleeding: List[str] = []

    module_labels = {
        "objective": "选填题",
        "big": "解答大题",
        "DS": "DS（数据结构）",
        "CO": "CO（计算机组成原理）",
        "OS": "OS（操作系统）",
        "CN": "CN（计算机网络）",
    }
    for mod_key, metrics in modules.items():
        acc = metrics.get("accuracy")
        if isinstance(acc, (int, float)) and acc >= 0.80:
            label = module_labels.get(mod_key, mod_key)
            strengths.append(
                f"{label}得分率达 {acc * 100:.1f}%（{format_number(float(metrics['score']))}/{format_number(float(metrics['max_score']))}），发挥稳健"
            )

    # 仅当本卷已记录错题时，0 错题的子科目才作为有据可查的稳固阵地
    if enriched_questions:
        for row in subsubject_rows:
            if row["total_wrong_count"] == 0:
                strengths.append(f"{row['subsubject']}在本卷已记录错题中 0 失误，基本盘稳固")
            elif row["objective_wrong_count"] == 0 and record.get("section") != "选填":
                strengths.append(f"{row['subsubject']}客观题 0 失误")

    # 阶段止血信号：前序套卷曾出错的考点 或 近期突破单考点，在本卷未再失分
    if enriched_questions:
        current_cids = {str(q["chapter_id"]) for q in enriched_questions if q.get("chapter_id")}
        current_topics = {str(q["topic"]) for q in enriched_questions if q.get("topic")}

        prior_topic_Counter: Counter = Counter()
        for prec in prior_records[-3:]:
            for pq in prec.get("wrong_questions") or []:
                ptopic = str(pq.get("topic") or "").strip()
                pcid = str(pq.get("chapter_id") or "").strip()
                if ptopic and ptopic not in current_topics and (not pcid or pcid not in current_cids):
                    prior_topic_Counter[ptopic] += 1

        for ptopic, count in prior_topic_Counter.most_common(3):
            stopped_bleeding.append(
                f"前序套卷暴露的「{ptopic}」（近3卷曾错 {count} 次）本卷未再失分（以已记录错题为准）"
            )

        for bt in parse_breakthroughs(archive_text):
            if bt.get("status") not in {"进行中", "已攻克"}:
                continue
            bt_tids = [t for t in bt.get("topic_ids") or [] if t]
            if bt_tids and all(tid not in current_cids for tid in bt_tids):
                stopped_bleeding.append(
                    f"突破单「{bt['goal']}」（{bt['status']}）对应考点本卷 0 失误"
                )

    return strengths, stopped_bleeding


def build_loss_ledger(
    record: Mapping[str, object],
    enriched_questions: Sequence[Mapping[str, object]],
) -> Dict[str, object]:
    """按四类失分账本聚合错题，并核算确定性客观题冤枉分与保底潜力分。"""
    subject = str(record["subject"])
    section = str(record.get("section") or "整卷")
    total_score = float(record["total_score"])
    max_score = (
        float(record["max_score"])
        if record.get("max_score") is not None
        else (
            float(objective_max_score(record["paper"], record["paper_type"]))
            if section == "选填"
            else float(SUBJECT_TOTALS.get(subject, 150.0))
        )
    )

    buckets: List[Dict[str, object]] = []
    for key, label, types, desc in LOSS_BUCKET_SPECS:
        items = [q for q in enriched_questions if q["bucket_key"] == key]
        obj_loss = sum(float(q["objective_points"]) for q in items if q["is_objective"])
        big_count = sum(1 for q in items if not q["is_objective"])
        buckets.append({
            "key": key,
            "label": label,
            "error_types": list(types),
            "count": len(items),
            "question_numbers": [int(q["question_number"]) for q in items],
            "objective_confirmed_loss": obj_loss,
            "big_question_count": big_count,
            "description": desc,
        })

    regret_bucket = next(b for b in buckets if b["key"] == "regrettable")
    confirmed_regret_obj_loss = float(regret_bucket["objective_confirmed_loss"])
    regret_big_count = int(regret_bucket["big_question_count"])
    potential_score = min(max_score, total_score + confirmed_regret_obj_loss)

    by_error_type = Counter(str(q["error_type"]) for q in enriched_questions)
    return {
        "total_score": total_score,
        "max_score": max_score,
        "total_lost_score": max(0.0, max_score - total_score),
        "confirmed_regret_objective_loss": confirmed_regret_obj_loss,
        "regret_big_question_count": regret_big_count,
        "potential_score_floor": potential_score,
        "error_type_counts": dict(by_error_type),
        "buckets": buckets,
    }


def build_issues_and_actions(
    record: Mapping[str, object],
    modules: Mapping[str, Mapping[str, object]],
    loss_ledger: Mapping[str, object],
    enriched_questions: Sequence[Mapping[str, object]],
    trigger_data: Mapping[str, object],
    target_score: Optional[float],
) -> Tuple[List[str], List[str], List[Dict[str, object]]]:
    """生成 ## 关键问题、## 下一步动作 与突破单推荐列表。"""
    subject = str(record["subject"])
    paper = str(record["paper"])
    total_score = float(record["total_score"])

    issues: List[str] = []
    actions: List[str] = []
    breakthrough_recommendations: List[Dict[str, object]] = []

    if record.get("issues"):
        issues.append(f"卷面主问题：{record['issues']}")

    if target_score is not None and record.get("section") != "选填":
        gap = total_score - target_score
        if gap < 0:
            issues.append(f"{subject}本卷总分 {format_number(total_score)}，距目标分 {format_number(target_score)} 还差 {format_number(abs(gap))} 分")

    # 低得分率模块预警
    module_names = {"objective": "选填题", "big": "解答大题", "DS": "DS", "CO": "CO", "OS": "OS", "CN": "CN"}
    for mod_key, metrics in modules.items():
        acc = metrics.get("accuracy")
        if isinstance(acc, (int, float)) and acc < 0.65:
            m_label = module_names.get(mod_key, mod_key)
            issues.append(
                f"{m_label}得分率偏低（{acc * 100:.1f}%，{format_number(float(metrics['score']))}/{format_number(float(metrics['max_score']))}）"
            )

    # 冤枉分预警
    regret_obj = float(loss_ledger["confirmed_regret_objective_loss"])
    regret_big = int(loss_ledger["regret_big_question_count"])
    if regret_obj > 0 or regret_big > 0:
        parts = []
        if regret_obj > 0:
            parts.append(f"客观题确定性冤枉分 {format_number(regret_obj)} 分")
        if regret_big > 0:
            parts.append(f"大题非智力失误 {regret_big} 道")
        issues.append(f"考场计算/策略冤枉失分偏高（{' + '.join(parts)}），追回后保底可达 {format_number(float(loss_ledger['potential_score_floor']))}+ 分")
        actions.append("针对本卷『计算失误/时间不够』题号，重做一遍验算步骤并设定单题止损时间线（选填 ≤ 5 分钟/题）")

    # 惯犯错题与突破单建议
    repeat_items = [q for q in enriched_questions if q["is_repeat_offender"]]
    if repeat_items:
        repeat_labels = [f"第{q['question_number']}题「{q['topic']}」（累计 {q['total_occurrences']} 次）" for q in repeat_items]
        issues.append(f"跨卷/历史惯犯暴露：{ '、'.join(repeat_labels) }")

    seen_bt_keys = set()
    for trig in trigger_data.get("triggered") or []:
        if trig.get("subject") != subject:
            continue
        cid = str(trig.get("chapter_id") or "")
        topic = str(trig.get("topic") or "")
        bt_key = cid or topic
        if bt_key in seen_bt_keys:
            continue
        seen_bt_keys.add(bt_key)
        rec = {
            "topic": topic,
            "chapter_id": cid,
            "reason": f"近期累计出错 {trig['count']} 次（{ '、'.join(trig.get('sources', [])[:3]) }）",
            "goal": f"攻克 {topic} 高频失分",
            "source": paper,
            "plan": f"Day1：重做本卷与同簇错题;Day2：无提示变式训练;Day3：/test 专项验收",
            "criteria": "连续 3 道同型题无提示一次做对",
        }
        breakthrough_recommendations.append(rec)
        actions.append(
            f"立项 3 天突破单攻克「{topic}」（近期已错 {trig['count']} 次）"
            + (f"，对口考点 ID：`{cid}`" if cid else "")
        )

    for q in repeat_items:
        bt_key = str(q["chapter_id"] or q["topic"])
        if bt_key in seen_bt_keys:
            continue
        seen_bt_keys.add(bt_key)
        cluster = q.get("cluster")
        if cluster and cluster.get("sibling_links"):
            actions.append(
                f"顺着元技能簇「{cluster['id']} · {cluster['name']}」连做同簇兄弟卡：{ '、'.join(cluster['sibling_links']) }"
            )
        else:
            actions.append(f"针对惯犯考点「{q['topic']}」（第{q['question_number']}题），回看错题卡并完成 2 道同章节变式")
        if int(q["total_occurrences"]) >= 3:
            breakthrough_recommendations.append({
                "topic": q["topic"],
                "chapter_id": q["chapter_id"],
                "reason": f"跨卷/历史累计第 {q['total_occurrences']} 次翻车",
                "goal": f"止血 {q['topic']} 顽固卡点",
                "source": f"{paper}第{q['question_number']}题",
                "plan": "Day1：复盘错题卡规范解法与卡点;Day2：同簇兄弟题连做;Day3：/test 验收",
                "criteria": "独立完成变式且不再触发同类错因",
            })

    # 尚未建卡的硬伤题提醒
    uncarded_hard = [
        q for q in enriched_questions
        if not q["has_card"] and q["bucket_key"] in {"hard_gap", "method_gap", "unclassified"}
    ]
    if uncarded_hard:
        nums = "、".join(f"第{q['question_number']}题" for q in uncarded_hard)
        actions.append(f"用 `/wrong` 补建本卷核心错题卡（{nums}），沉淀规范解法与考场口诀")

    if not issues:
        issues.append(f"{subject} {paper} 整体发挥平稳，未见集中崩盘模块")
    if not actions:
        actions.append("按 SRS 计划正常推进到期错题复习，保持当前做题手感")

    return issues, actions, breakthrough_recommendations


def render_markdown_report(
    record: Mapping[str, object],
    prev_record: Optional[Mapping[str, object]],
    target_score: Optional[float],
    modules: Mapping[str, Mapping[str, object]],
    subsubject_rows: Sequence[Mapping[str, object]],
    strengths: Sequence[str],
    stopped_bleeding: Sequence[str],
    loss_ledger: Mapping[str, object],
    enriched_questions: Sequence[Mapping[str, object]],
    issues: Sequence[str],
    actions: Sequence[str],
    breakthrough_recommendations: Sequence[Mapping[str, object]],
) -> str:
    subject = str(record["subject"])
    paper = str(record["paper"])
    paper_type = str(record["paper_type"])
    section = str(record.get("section") or "整卷")
    exam_date = str(record["exam_date"])
    total_score = float(record["total_score"])
    max_score = float(loss_ledger["max_score"])

    # 1. 卷面基本盘与优势阵地
    if prev_record and prev_record.get("total_score") is not None:
        delta = total_score - float(prev_record["total_score"])
        sign = "+" if delta > 0 else ""
        prev_str = f"{sign}{format_number(delta)} 分（上卷 {prev_record['paper']}：{format_number(float(prev_record['total_score']))} 分）"
    else:
        prev_str = "首次记录该类型套卷"

    if target_score is not None and section != "选填":
        t_gap = total_score - target_score
        t_sign = "+" if t_gap >= 0 else ""
        target_str = f"目标 {format_number(target_score)} 分（差值 {t_sign}{format_number(t_gap)} 分）"
    else:
        target_str = "未设单科目标或为专项练习"

    overview_lines = [
        f"- **卷型 / 范围**：{paper_type} · {section}",
        f"- **卷面得分**：**{format_number(total_score)}** / {format_number(max_score)} 分｜{target_str}",
        f"- **趋势对比**：{prev_str}",
    ]
    if record.get("note"):
        overview_lines.append(f"- **考场备注**：{record['note']}")

    if modules:
        mod_parts = []
        mod_names = {"objective": "选填", "big": "大题", "DS": "DS", "CO": "CO", "OS": "OS", "CN": "CN"}
        for k, m in modules.items():
            label = mod_names.get(k, k)
            if "accuracy" in m and "score" in m:
                mod_parts.append(
                    f"{label} {format_number(float(m['score']))}/{format_number(float(m['max_score']))}（{float(m['accuracy']) * 100:.1f}%）"
                )
        if mod_parts:
            overview_lines.append(f"- **模块得分率**：{' ｜ '.join(mod_parts)}")

    if subsubject_rows:
        sub_parts = []
        for row in subsubject_rows:
            nums_str = f"（题号：{','.join(map(str, row['question_numbers']))}）" if row["question_numbers"] else ""
            if subject == "数学一":
                sub_parts.append(
                    f"{row['subsubject']}错 {row['total_wrong_count']} 题"
                    f"［选填推算 {format_number(float(row['objective_estimated_score']))}/{format_number(float(row['objective_max']))}］{nums_str}"
                )
            else:
                sub_parts.append(f"{row['subsubject']}错 {row['total_wrong_count']} 题{nums_str}")
        overview_lines.append(f"- **分科错题分布**：{' ｜ '.join(sub_parts)}")

    if strengths:
        overview_lines.append(f"- **✨ 稳固阵地**：{'；'.join(strengths)}")
    if stopped_bleeding:
        overview_lines.append(f"- **✅ 阶段止血信号**：{'；'.join(stopped_bleeding)}")

    # 2. 失分账本
    regret_obj = float(loss_ledger["confirmed_regret_objective_loss"])
    regret_big = int(loss_ledger["regret_big_question_count"])
    potential = float(loss_ledger["potential_score_floor"])
    regret_extra = f"（另含 {regret_big} 道大题存在非智力失误）" if regret_big > 0 else ""
    ledger_lines = [
        f"- **实力底线 vs 修正潜力分**：当前实得 **{format_number(total_score)}** 分；仅追回已确认的客观题冤枉分（**{format_number(regret_obj)}** 分），卷面保底可达 **{format_number(potential)}** 分{regret_extra}。",
        "",
        "| 失分性质 | 包含错因 | 题数 | 涉及题号 | 客观题确定失分 | 教练诊断 |",
        "|---|---|---:|---|---:|---|",
    ]
    for b in loss_ledger["buckets"]:
        if b["count"] == 0 and b["key"] == "unclassified":
            continue
        nums = "、".join(f"#{n}" for n in b["question_numbers"]) if b["question_numbers"] else "-"
        obj_str = f"{format_number(float(b['objective_confirmed_loss']))} 分" if b["objective_confirmed_loss"] else "0 分"
        ledger_lines.append(
            f"| {b['label']} | {'/'.join(b['error_types'])} | {b['count']} | {nums} | {obj_str} | {b['description']} |"
        )

    # 3. 错题深度串联
    if not enriched_questions:
        wrong_section = "- 本卷未记录具体错题或全卷无错题。若尚未归档错题，可先用 `/wrong` 建卡或在 `/score` 中传入 `--wrong-questions` 后重跑 `/paper`。"
    else:
        wrong_lines = [
            "| 题号 | 分科 / 题型 | 规范章节与考点 | 错因 | 惯犯/初犯 | 当前掌握状态 | 错题卡与元技能簇 |",
            "|---:|---|---|---|---|---|---|",
        ]
        detail_lines = ["", "### 逐题穿透与同簇串联"]
        for q in enriched_questions:
            badge = f"🚨 惯犯（累计{q['total_occurrences']}次）" if q["is_repeat_offender"] else "🆕 初犯"
            if q["has_card"] and q.get("progress"):
                light = LIGHTS.get(str(q["status"]), "⚪")
                status_cell = f"{light} {q['status']}（{q['progress']['summary']}）"
            else:
                status_cell = "未建卡"
            card_cell = q["wikilink"] if q["has_card"] else "未建卡（轻量记录）"
            if q.get("cluster"):
                card_cell += f"<br>簇：`{q['cluster']['id']}` {q['cluster']['name']}"
            wrong_lines.append(
                f"| #{q['question_number']} | {q['subsubject']}·{q['question_type']} | "
                f"{q['chapter_display']} · **{q['topic']}** | {q['error_type']} | {badge} | {status_cell} | {card_cell} |"
            )

            detail_parts = [
                f"- **第 {q['question_number']} 题（{q['subsubject']} · {q['topic']}）**［{badge}｜{q['error_type']}］：{q['mistake_summary']}"
            ]
            if q["prior_sources"]:
                detail_parts.append(f"  - 历史翻车轨迹：{'、'.join(q['prior_sources'])}")
            if q.get("cluster") and q["cluster"].get("sibling_links"):
                detail_parts.append(
                    f"  - 同元技能簇（`{q['cluster']['id']}` {q['cluster']['name']}）兄弟题：{'、'.join(q['cluster']['sibling_links'])}"
                )
            detail_lines.extend(detail_parts)
        wrong_section = "\n".join(wrong_lines + detail_lines)

    # 4. 本卷考前复盘口诀清单
    hooks = [
        f"- **#{q['question_number']} {q['topic']}**：{q['action_hook']}"
        for q in enriched_questions
        if q.get("action_hook")
    ]
    if hooks:
        hooks_section = "\n".join(hooks)
    else:
        hooks_section = "- 暂无已提取的卡片口诀（用 `/wrong` 归档本卷核心错题后，此处会自动汇总每道题的『下次怎么做 / 记忆钩子』）。"

    # 5. 关键问题 & 下一步动作
    issues_section = "\n".join(f"- {item}" for item in issues)
    actions_lines = [f"- {item}" for item in actions]
    if breakthrough_recommendations:
        actions_lines.append("")
        actions_lines.append("### 突破单立项建议")
        for rec in breakthrough_recommendations:
            tid_part = f" `--topic-id {rec['chapter_id']}`" if rec.get("chapter_id") else ""
            actions_lines.append(
                f"- **{rec['goal']}**（触发原因：{rec['reason']}）→ 可执行：`manage_breakthrough.py create --goal \"{rec['goal']}\" --source \"{rec['source']}\" --plan \"{rec['plan']}\" --criteria \"{rec['criteria']}\"{tid_part}`"
            )
    actions_section = "\n".join(actions_lines)

    template = load_template_markdown("套卷分析模板.md")
    rendered = template
    for k, v in {
        "subject": subject,
        "paper": paper,
        "exam_date": exam_date,
        "overview_section": "\n".join(overview_lines),
        "loss_ledger_section": "\n".join(ledger_lines),
        "wrong_questions_section": wrong_section,
        "action_hooks_section": hooks_section,
        "key_issues": issues_section,
        "next_actions": actions_section,
    }.items():
        rendered = rendered.replace(f"{{{k}}}", v)
    return rendered.rstrip() + "\n"


def parse_args() -> Tuple[Optional[str], str, argparse.Namespace]:
    parser = argparse.ArgumentParser(description="生成单套试卷深度分析报告并写入 复盘报告/")
    parser.add_argument("pos_first", nargs="?", default=None, help="Obsidian 根目录或科目")
    parser.add_argument("pos_second", nargs="?", default=None, help="科目（当第一个位置参数为根目录时）")
    parser.add_argument("--subject", dest="subject_flag", help="科目：数学一 / 408 / 英语一 / 政治")
    parser.add_argument("--paper", help="卷子名称；省略时默认取该科目最新一条成绩记录")
    parser.add_argument("--paper-type", choices=["真题", "模拟"], help="卷型（新记成绩时可指定，缺省自动推断）")
    parser.add_argument("--section", choices=["整卷", "选填"], default="整卷", help="练习范围，默认整卷")
    parser.add_argument("--date", "--exam-date", dest="exam_date", help="考试日期 YYYY-MM-DD")
    parser.add_argument("--total", help="可选：若尚未执行 /score，可直接传入总分一并记录成绩")
    parser.add_argument("--issues", default="", help="主要问题（配合 --total 使用）")
    parser.add_argument("--note", default="", help="补充备注（配合 --total 使用）")
    parser.add_argument("--wrong-questions", help='卷面错题，格式 "3:没思路;8:算错"')
    parser.add_argument("--question-topics", help='可选考点标注，格式 "3:二重积分;8:泰勒展开"')
    parser.add_argument(
        "--mode",
        choices=["auto", "analyze", "review"],
        default="auto",
        help="运行模式：auto（未复盘则新建报告 analyze，已复盘则进入二刷复习 review）",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅输出 JSON 与 Markdown 预览，不写入文件")

    for field in _all_extra_fields():
        parser.add_argument(_field_to_cli(field))

    args = parser.parse_args()
    obsidian_root_arg: Optional[str] = None
    subject_raw: Optional[str] = args.subject_flag

    if args.pos_first and args.pos_second:
        obsidian_root_arg = args.pos_first
        subject_raw = subject_raw or args.pos_second
    elif args.pos_first:
        if args.pos_first in SUBJECT_ALIASES and not subject_raw:
            subject_raw = args.pos_first
        else:
            obsidian_root_arg = args.pos_first

    if not subject_raw:
        json_error("必须提供科目（如：数学一 / 408 / 英语一 / 政治）")
    subject = normalize_subject(subject_raw)
    return obsidian_root_arg, subject, args


def _collect_extra_fields(subject: str, args: argparse.Namespace) -> Dict[str, Optional[float]]:
    fields: Dict[str, Optional[float]] = {}
    relevant_fields = list(SUBJECT_SCORE_FIELDS.get(subject, ())) + list(LOSS_FIELDS_BY_SUBJECT.get(subject, ()))
    for field in relevant_fields:
        cli_name = _field_to_cli(field)
        fields[field] = parse_non_negative_number(getattr(args, field, None), cli_name.lstrip("-"))
    return fields


def resolve_or_create_record(
    obsidian_root: Path,
    subject: str,
    args: argparse.Namespace,
) -> Dict[str, object]:
    """定位目标卷子的成绩记录；若传入了 --total 则先写入/更新成绩记录。"""
    section = args.section
    if args.total is not None:
        if not args.paper:
            json_error("传入 --total 记录成绩时，必须同时指定 --paper 卷名")
        exam_day = date.fromisoformat(args.exam_date).isoformat() if args.exam_date else date.today().isoformat()
        paper_type = args.paper_type or infer_paper_type(args.paper)
        try:
            _question_limit(subject, args.paper, paper_type, section)
            wrong_questions = build_wrong_questions(
                args.wrong_questions, args.question_topics, subject, exam_day, args.paper, paper_type, section
            )
            linked, _ = associate_cards(obsidian_root, subject, args.paper, exam_day, paper_type, section)
            if args.wrong_questions is None:
                wrong_questions = linked or None
            elif wrong_questions:
                by_number = {q["question_number"]: q for q in linked}
                wrong_questions = [{**by_number.get(q["question_number"], {}), **q} for q in wrong_questions]
        except ValueError as exc:
            json_error(str(exc))

        total_score = parse_non_negative_number(args.total, "total")
        assert total_score is not None
        extra_fields = _collect_extra_fields(subject, args)
        if section == "选填":
            extra_fields = {"score_objective": total_score, "loss_objective": extra_fields.get("loss_objective")}
        else:
            validate_score_breakdown(subject, total_score, extra_fields)

        mode = "" if args.wrong_questions is None else ("clear" if not wrong_questions else "manual")
        if args.dry_run:
            return {
                "path": "",
                "subject": subject,
                "paper": args.paper,
                "paper_type": paper_type,
                "section": section,
                "max_score": objective_max_score(args.paper, paper_type) if section == "选填" else None,
                "exam_date": exam_day,
                "total_score": total_score,
                "issues": args.issues,
                "note": args.note,
                "wrong_questions": wrong_questions or [],
                "wrong_questions_mode": mode or ("auto" if wrong_questions else ""),
                **extra_fields,
            }

        try:
            record_path = write_score_record(
                obsidian_root=obsidian_root,
                subject=subject,
                paper=args.paper,
                paper_type=paper_type,
                exam_day=exam_day,
                total_score=total_score,
                issues=args.issues,
                note=args.note,
                extra_fields=extra_fields,
                wrong_questions=wrong_questions,
                wrong_questions_mode=mode,
                section=section,
            )
        except ValueError as exc:
            json_error(str(exc))

        record = parse_score_record(record_path)
        assert record is not None
        row = build_summary_row_from_record(record)
        archive_path, archive_text = load_archive_text(obsidian_root)
        if section == "选填":
            updated_archive = upsert_math_objective_score_row(archive_text, {**row, "max_score": str(record["max_score"])})
        else:
            updated_archive = upsert_subject_score_row(archive_text, subject, row)
        updated_archive = update_archive_date(updated_archive, exam_day)
        atomic_write(archive_path, updated_archive)
        return record

    records = collect_score_records(obsidian_root, [subject], section=section)
    if args.paper:
        target_key = paper_key(source_paper(args.paper))
        records = [r for r in records if paper_key(source_paper(str(r["paper"]))) == target_key]
    if args.exam_date:
        exam_day = date.fromisoformat(args.exam_date).isoformat()
        records = [r for r in records if str(r["exam_date"]) == exam_day]
    if not records:
        hint = f"（卷名：{args.paper}）" if args.paper else ""
        json_error(
            f"未找到 {subject} {section} 成绩记录{hint}。请先运行 /score 记录成绩，或在调用 build_paper_report.py 时直接传入 --paper 与 --total。"
        )
    # 未显式指定卷名和日期时：若存在尚未生成复盘报告的套卷，优先定位最新一套未复盘套卷（除非强制 --mode review）
    if not args.paper and not args.exam_date and args.mode != "review":
        unanalyzed = [
            r for r in records
            if not build_report_path(
                obsidian_root, str(r["exam_date"]), subject, str(r["paper"]), str(r.get("section") or "整卷")
            ).exists()
        ]
        if unanalyzed:
            return unanalyzed[-1]
    return records[-1]


def main() -> None:
    obsidian_root_arg, subject, args = parse_args()
    obsidian_root = resolve_obsidian_root(obsidian_root_arg)

    try:
        record = resolve_or_create_record(obsidian_root, subject, args)
        all_records = collect_score_records(obsidian_root, [subject], section=str(record.get("section") or "整卷"))
        all_cards = [c for c in iter_review_cards(obsidian_root) if not c["icloud_placeholder"]]

        # 查找同科目、同 section 的上一套卷子记录
        cur_pkey = paper_key(source_paper(str(record["paper"])))
        cur_date = str(record["exam_date"])
        prior_records = [
            r for r in all_records
            if (str(r["exam_date"]), paper_key(source_paper(str(r["paper"])))) != (cur_date, cur_pkey)
            and str(r["exam_date"]) <= cur_date
        ]
        prev_record = prior_records[-1] if prior_records else None

        raw_wrong, link_warnings = collect_merged_wrong_questions(obsidian_root, record)
        enriched_questions = enrich_wrong_questions(obsidian_root, record, raw_wrong, all_cards, all_records)
        modules = module_scores(record)
        subsubject_rows = build_subsubject_summary(
            subject, str(record["paper"]), str(record["paper_type"]), str(record.get("section") or "整卷"), enriched_questions
        )

        _, archive_text = load_archive_text(obsidian_root)
        targets = parse_subject_targets(archive_text)
        target_score = targets.get(subject)

        strengths, stopped_bleeding = build_strengths_and_stopped_bleeding(
            record, modules, subsubject_rows, enriched_questions, prior_records, archive_text
        )
        loss_ledger = build_loss_ledger(record, enriched_questions)
        trigger_data = check_triggers(obsidian_root, date.fromisoformat(cur_date), days=3)
        issues, actions, bt_recommendations = build_issues_and_actions(
            record, modules, loss_ledger, enriched_questions, trigger_data, target_score
        )

        markdown = render_markdown_report(
            record=record,
            prev_record=prev_record,
            target_score=target_score,
            modules=modules,
            subsubject_rows=subsubject_rows,
            strengths=strengths,
            stopped_bleeding=stopped_bleeding,
            loss_ledger=loss_ledger,
            enriched_questions=enriched_questions,
            issues=issues,
            actions=actions,
            breakthrough_recommendations=bt_recommendations,
        )

        report_path = build_report_path(
            obsidian_root, cur_date, subject, str(record["paper"]), str(record.get("section") or "整卷")
        )
        report_existed = report_path.exists()
        if args.mode in {"analyze", "review"}:
            effective_mode = args.mode
        elif args.total is not None or not report_existed:
            effective_mode = "analyze"
        else:
            effective_mode = "review"

        review_summary, review_queue = build_paper_review_queue(enriched_questions)

        if not args.dry_run:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(report_path, markdown)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        json_error(str(exc))

    output: Dict[str, object] = {
        "error": False,
        "dry_run": args.dry_run,
        "mode": effective_mode,
        "report_existed": report_existed,
        "report_path": str(report_path),
        "score_record_path": str(record.get("path") or ""),
        "subject": subject,
        "paper": record["paper"],
        "paper_type": record["paper_type"],
        "section": record.get("section", "整卷"),
        "exam_date": record["exam_date"],
        "total_score": record["total_score"],
        "target_score": target_score,
        "previous_paper": (
            {"paper": prev_record["paper"], "exam_date": prev_record["exam_date"], "total_score": prev_record["total_score"]}
            if prev_record
            else None
        ),
        "modules": modules,
        "subsubjects": subsubject_rows,
        "strengths": strengths,
        "stopped_bleeding": stopped_bleeding,
        "loss_ledger": loss_ledger,
        "wrong_questions": enriched_questions,
        "linked_card_count": sum(1 for q in enriched_questions if q["has_card"]),
        "repeat_offender_count": sum(1 for q in enriched_questions if q["is_repeat_offender"]),
        "first_time_count": sum(1 for q in enriched_questions if not q["is_repeat_offender"]),
        "review_summary": review_summary,
        "review_queue": review_queue,
        "key_issues": issues,
        "next_actions": actions,
        "breakthrough_recommendations": bt_recommendations,
        "markdown": markdown,
    }
    if link_warnings:
        output["link_warnings"] = link_warnings
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
