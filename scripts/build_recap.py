#!/usr/bin/env python3
"""汇总指定周期的日志与复习记录，生成复盘报告。

用法:
  python3 build_recap.py [OBSIDIAN_ROOT] [--period week|month] [--today YYYY-MM-DD]
  环境变量 KAOYAN_OBSIDIAN_ROOT 可替代 CLI 参数

默认为周复盘。加 --period month 做月复盘。
"""
import argparse
import calendar
import json
import re
from datetime import date, timedelta
from pathlib import Path

from archive_ops import (
    extract_list_items,
    extract_section_block,
    infer_subject_mentions,
    load_archive_text,
    load_template_markdown,
    parse_score_cell,
    parse_subject_score_rows,
)
from constants import LEGACY_HEADING_INDENT_LIMIT
from env_util import atomic_write, resolve_obsidian_root
from frontmatter import parse_frontmatter
from knowledge_map_parser import load_all_maps
from note_scan import (
    NoteEntry,
    extract_chapter_num,
    normalize_subgroup,
    render_recap_notes_block,
    scan_all_notes,
    scan_notes_in_range,
)
from study_ops import PLAN_SUBJECTS, format_hours, parse_today

HISTORY_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) - (不会|半会|会) -", re.M)
LEGACY_SCORE_SECTION_RE = re.compile(
    rf"^[ \t]{{0,{LEGACY_HEADING_INDENT_LIMIT}}}## 训练成绩记录\r?\n"
    rf"(.*?)(?=^[ \t]{{0,{LEGACY_HEADING_INDENT_LIMIT}}}## |\Z)",
    re.M | re.S,
)


def get_date_range(today, period):
    """根据周期返回 (start, end, label, filename)。"""
    if period == "month":
        start = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        end = today.replace(day=last_day)
        label = f"{today.year}年{today.month:02d}月"
        filename = f"{today.strftime('%Y-%m')}-月复盘.md"
    else:
        monday = today - timedelta(days=today.weekday())
        end = monday + timedelta(days=6)
        start = monday
        iso_year, iso_week_num, _ = monday.isocalendar()
        label = f"{iso_year}-W{iso_week_num:02d}"
        filename = f"{label}-周复盘.md"
    return start, end, label, filename


def parse_logged_hours(text):
    match = re.search(r"时长[^0-9]*([0-9]+(?:\.[0-9]+)?)", text)
    return float(match.group(1)) if match else 0.0
def recap_hours(value):
    return f"{format_hours(value)} 小时"


def build_bullets(items, fallback):
    if not items:
        return fallback
    return "\n".join(f"- {item}" for item in items[:5])


def format_number(value):
    if abs(value - int(value)) < 1e-9:
        return str(int(value))
    return f"{value:.1f}"


def parse_score_records(text, log_day):
    block = extract_section_block(text, "训练成绩记录")
    if not block:
        legacy_match = LEGACY_SCORE_SECTION_RE.search(text)
        block = legacy_match.group(1).strip("\r\n") if legacy_match else ""
    records = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
        if len(cells) != 7 or cells[0] in {"科目", "------"} or set(cells[0]) == {"-"}:
            continue
        if not cells[3] or not cells[4]:
            continue
        score_match = re.search(r"([0-9]+(?:\.[0-9]+)?)", cells[3])
        total_match = re.search(r"([0-9]+(?:\.[0-9]+)?)", cells[4])
        if not score_match or not total_match:
            continue
        score = float(score_match.group(1))
        total = float(total_match.group(1))
        if total <= 0:
            continue
        records.append({
            "date": log_day,
            "subject": cells[0],
            "kind": cells[1],
            "source": cells[2],
            "score": score,
            "total": total,
            "note": cells[6] if cells[6] != "-" else "",
        })
    return records


def normalize_score_identity(record):
    source = re.sub(r"^(真题|模拟)\s+", "", record["source"]).strip()
    return (
        record["date"],
        "数学一" if record["subject"] == "数学" else record["subject"],
        re.sub(r"\s+", "", source),
        round(record["score"], 4),
        round(record["total"], 4),
    )


def merge_score_records(primary_records, extra_records):
    seen = {normalize_score_identity(record) for record in primary_records}
    merged = list(primary_records)
    for record in extra_records:
        identity = normalize_score_identity(record)
        if identity in seen:
            continue
        seen.add(identity)
        merged.append(record)
    return merged


def collect_logs(obsidian_root, start, end):
    """扫描日期范围内的学习日志。"""
    log_dir = Path(obsidian_root) / "学习日志"
    highlights, blockers = [], []
    logged_days = 0
    total_hours = 0.0
    score_records = []

    current = start
    while current <= end:
        log_path = log_dir / f"{current.isoformat()}.md"
        if log_path.exists():
            try:
                text = log_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                current += timedelta(days=1)
                continue
            logged_days += 1
            total_hours += parse_logged_hours(text)
            highlights.extend(extract_list_items(text, "学到了什么"))
            blockers.extend(extract_list_items(text, "卡壳与挣扎"))
            score_records.extend(parse_score_records(text, current))
        current += timedelta(days=1)
    return highlights, blockers, logged_days, total_hours, score_records


def collect_archive_subject_scores(obsidian_root, start, end):
    try:
        _, archive_text = load_archive_text(obsidian_root)
    except FileNotFoundError:
        return []

    records = []
    subject_totals = {"数学一": 150.0, "408": 150.0, "英语一": 100.0}
    for subject in ("数学一", "408", "英语一"):
        for row in parse_subject_score_rows(archive_text, subject):
            try:
                row_day = date.fromisoformat(row["date"])
            except ValueError:
                continue
            if not (start <= row_day <= end):
                continue
            score_value = parse_score_cell(row["total"])
            if score_value is None:
                continue
            note_parts = []
            if subject == "408" and all(key in row for key in ("ds", "co", "os", "cn")):
                note_parts.append(
                    "模块错题：DS {ds} / CO {co} / OS {os} / CN {cn}".format(
                        ds=row["ds"],
                        co=row["co"],
                        os=row["os"],
                        cn=row["cn"],
                    )
                )
            if row["issues"] and row["issues"] != "-":
                note_parts.append(f"主要问题：{row['issues']}")
            if row["note"] and row["note"] != "-":
                note_parts.append(row["note"])
            records.append({
                "date": row_day,
                "subject": subject,
                "kind": "模拟",
                "source": f"{row.get('paper_type', '模拟')} {row['paper']}".strip(),
                "score": score_value,
                "total": subject_totals[subject],
                "note": "；".join(note_parts),
            })
    return records


def collect_review_stats(obsidian_root, start, end):
    """扫描日期范围内的错题卡复习历史。"""
    root = Path(obsidian_root) / "错题本"
    status_counts = {"不会": 0, "半会": 0, "会": 0}
    subject_counts = {subject: 0 for subject in PLAN_SUBJECTS}

    if not root.exists():
        return 0, status_counts, subject_counts

    for md_file in root.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        _, body, _ = parse_frontmatter(text)
        rel = md_file.relative_to(root)
        subject = rel.parts[0] if rel.parts else ""
        for history_date, status in HISTORY_RE.findall(body):
            try:
                day = date.fromisoformat(history_date)
            except ValueError:
                continue
            if start <= day <= end:
                status_counts[status] += 1
                if subject in subject_counts:
                    subject_counts[subject] += 1

    return sum(status_counts.values()), status_counts, subject_counts


def _card_chapter_and_subgroup_from_path(rel_parts):
    """从 错题本/{科目}/.../{file}.md 的路径段里抽出 (chapter_raw, chapter_num, subgroup)。

    错题本目录深度可能是 2~5 层（含文件名），且 subgroup 是可选的：
    - `错题本/{科目}/{子科目}/{章}/{节}/{file}`（5 段，数学一最深）
    - `错题本/{科目}/{子科目}/{章}/{file}`（4 段）
    - `错题本/{科目}/{章}/{file}`（3 段，无 subgroup）
    - `错题本/{科目}/{file}`（2 段，没分章）

    策略：跳过最后的文件名，先找含「章」的段当 chapter；找不到再退化到第一个能解出 chapter_num 的段。
    chapter 之前的那段（如果还有）就是 subgroup。
    """
    middle = list(rel_parts[1:-1])
    if not middle:
        return "", None, ""

    chapter_idx = None
    for i, part in enumerate(middle):
        if "章" in part and extract_chapter_num(part) is not None:
            chapter_idx = i
            break
    if chapter_idx is None:
        for i, part in enumerate(middle):
            if extract_chapter_num(part) is not None:
                chapter_idx = i
                break

    if chapter_idx is None:
        # 没找到可识别章节，把第一段当 subgroup 兜底，章节为空
        return "", None, middle[0] if middle else ""

    chapter_raw = middle[chapter_idx]
    chapter_num = extract_chapter_num(chapter_raw)
    subgroup = middle[chapter_idx - 1] if chapter_idx >= 1 else ""
    return chapter_raw, chapter_num, subgroup


def _card_chapter_from_path(rel_parts):
    """向后兼容的薄包装。"""
    chapter_raw, _, _ = _card_chapter_and_subgroup_from_path(rel_parts)
    return chapter_raw


def collect_wrong_exposure(obsidian_root, start, end):
    """扫描错题本，统计周期内的「错题暴露」：

    - new_cards: first_wrong_at 在周期内的新建卡数 + 按 (科目, chapter_num) 分布
    - stubborn: 周期内复习仍判 `不会` 或 `不会` 次数 ≥ 2 的卡（TOP 5 by recent 不会次数）
    - chapter_activity: 周期内每个 (科目, chapter_num) 的错题活跃信号（新增 + 复习失败）
    """
    root = Path(obsidian_root) / "错题本"
    new_cards = []          # list of {subject, chapter_num, chapter_raw, topic, path}
    stubborn_cards = []     # list of {fail_in_range, latest_date, subject, topic, path, chapter_num}
    chapter_activity = {}   # (subject, chapter_num) -> {"new": n, "fail": n, "chapter_raw": s}

    if not root.exists():
        return {
            "new_cards": new_cards,
            "stubborn_cards": stubborn_cards,
            "chapter_activity": chapter_activity,
        }

    for md_file in root.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm, body, _ = parse_frontmatter(text)
        rel = md_file.relative_to(root)
        subject = rel.parts[0] if rel.parts else ""
        if subject not in PLAN_SUBJECTS:
            continue
        chapter_raw, chapter_num, subgroup_raw = _card_chapter_and_subgroup_from_path(rel.parts)
        subgroup = normalize_subgroup(subject, subgroup_raw)
        topic = str(fm.get("topic", "")).strip() or md_file.stem
        path_rel = str(md_file.relative_to(obsidian_root))

        # 新增卡：first_wrong_at 在周期内
        first_wrong = str(fm.get("first_wrong_at", "")).strip()
        try:
            first_day = date.fromisoformat(first_wrong) if first_wrong else None
        except ValueError:
            first_day = None
        is_new_in_range = first_day is not None and start <= first_day <= end
        if is_new_in_range:
            new_cards.append({
                "subject": subject,
                "subgroup": subgroup,
                "chapter_num": chapter_num,
                "chapter_raw": chapter_raw,
                "topic": topic,
                "path": path_rel,
            })

        # 周期内复习历史
        fail_in_range = 0
        latest_status_in_range = None
        latest_day_in_range = None
        for history_date, status in HISTORY_RE.findall(body):
            try:
                day = date.fromisoformat(history_date)
            except ValueError:
                continue
            if not (start <= day <= end):
                continue
            if status == "不会":
                fail_in_range += 1
            if latest_day_in_range is None or day > latest_day_in_range:
                latest_day_in_range = day
                latest_status_in_range = status

        is_stubborn = (latest_status_in_range == "不会") or (fail_in_range >= 2)
        if is_stubborn:
            stubborn_cards.append({
                "fail_in_range": fail_in_range,
                "latest_day": latest_day_in_range.isoformat() if latest_day_in_range else "",
                "subject": subject,
                "subgroup": subgroup,
                "topic": topic,
                "path": path_rel,
                "chapter_num": chapter_num,
            })

        # 章节活跃（用三元键避免不同子科目同章号撞车）
        if chapter_num is not None:
            key = (subject, subgroup, chapter_num)
            slot = chapter_activity.setdefault(key, {"new": 0, "fail": 0, "chapter_raw": chapter_raw})
            if is_new_in_range:
                slot["new"] += 1
            slot["fail"] += fail_in_range

    # stubborn sorted by fail_in_range desc, latest_day desc
    stubborn_cards.sort(key=lambda x: (x["fail_in_range"], x["latest_day"]), reverse=True)

    return {
        "new_cards": new_cards,
        "stubborn_cards": stubborn_cards,
        "chapter_activity": chapter_activity,
    }


def collect_cross_signals(notes, wrong_exposure):
    """以 (subject, subgroup, chapter_num) 为键，对照笔记与错题活跃度。

    - only-drilling: 新增/失败错题 ≥ 3 但本周笔记 = 0
    - only-theory: 笔记 ≥ 2 但本周错题活跃 = 0
    - healthy: 两者都 > 0

    使用三元键避免数学一·高数·第1章 和 数学一·线代·第1章 被错误合并。
    """
    note_counts = {}   # (subject, subgroup, chapter_num) -> count
    chapter_raw_map = {}
    for note in notes:
        if note.chapter_num is None:
            continue
        subgroup = normalize_subgroup(note.subject, note.subgroup)
        key = (note.subject, subgroup, note.chapter_num)
        note_counts[key] = note_counts.get(key, 0) + 1
        chapter_raw_map.setdefault(key, note.chapter_raw)

    activity = wrong_exposure["chapter_activity"]

    only_drilling = []
    only_theory = []
    healthy = []

    for key, slot in activity.items():
        wrong_score = slot["new"] + slot["fail"]
        note_count = note_counts.get(key, 0)
        chapter_raw = slot["chapter_raw"]
        if wrong_score >= 3 and note_count == 0:
            only_drilling.append({"key": key, "wrong": wrong_score, "chapter_raw": chapter_raw})
        elif note_count > 0 and wrong_score > 0:
            healthy.append({"key": key, "wrong": wrong_score, "notes": note_count, "chapter_raw": chapter_raw})

    for key, note_count in note_counts.items():
        slot = activity.get(key, {"new": 0, "fail": 0})
        if note_count >= 2 and (slot["new"] + slot["fail"]) == 0:
            only_theory.append({"key": key, "notes": note_count, "chapter_raw": chapter_raw_map.get(key, "")})

    only_drilling.sort(key=lambda x: x["wrong"], reverse=True)
    only_theory.sort(key=lambda x: x["notes"], reverse=True)

    return {
        "only_drilling": only_drilling,
        "only_theory": only_theory,
        "healthy": healthy,
    }


def _infer_subgroup_from_map(subject, chapter_num, maps):
    """错题路径没写 subgroup 时，靠知识地图反推：

    如果该 chapter_num 在该科目下只命中一个 subgroup，就用那个；模糊则返回空串。
    """
    if subject not in maps or chapter_num is None:
        return ""
    matches = {e.subgroup for e in maps[subject] if e.chapter_num == chapter_num}
    if len(matches) == 1:
        return matches.pop()
    return ""


def collect_coverage(obsidian_root):
    """月复盘专用：对照知识地图，统计每科笔记/错题的章节覆盖度。

    用 (subject, subgroup, chapter_num) 作 join 键，避免不同子科目同章号被合并。
    错题路径里 subgroup 缺失时，会尝试从知识地图反推（chapter 号唯一时）。
    返回 {subject: {total, with_notes, with_wrongs, blank_chapters: [(num, name, subgroup), ...]}}.
    blank_chapters: 既无笔记又无错题的章节，最多列 10 个。
    """
    maps = load_all_maps(Path(obsidian_root))
    if not maps:
        return {}

    all_notes = scan_all_notes(Path(obsidian_root))
    notes_by_chapter = {}  # (subject, subgroup, chapter_num) -> count
    for note in all_notes:
        if note.chapter_num is None:
            continue
        sg = normalize_subgroup(note.subject, note.subgroup)
        if not sg:
            sg = _infer_subgroup_from_map(note.subject, note.chapter_num, maps)
        key = (note.subject, sg, note.chapter_num)
        notes_by_chapter[key] = notes_by_chapter.get(key, 0) + 1

    # 扫错题本：哪些 (subject, subgroup, chapter_num) 出现过卡
    wrong_chapters = set()
    root = Path(obsidian_root) / "错题本"
    if root.exists():
        for md_file in root.rglob("*.md"):
            try:
                rel = md_file.relative_to(root)
            except ValueError:
                continue
            if not rel.parts:
                continue
            subject = rel.parts[0]
            if subject not in PLAN_SUBJECTS:
                continue
            _, chapter_num, subgroup_raw = _card_chapter_and_subgroup_from_path(rel.parts)
            if chapter_num is None:
                continue
            sg = normalize_subgroup(subject, subgroup_raw)
            if not sg:
                sg = _infer_subgroup_from_map(subject, chapter_num, maps)
            wrong_chapters.add((subject, sg, chapter_num))

    result = {}
    for subject, entries in maps.items():
        total = len(entries)
        with_notes = sum(
            1 for e in entries
            if notes_by_chapter.get((subject, e.subgroup, e.chapter_num), 0) > 0
        )
        with_wrongs = sum(
            1 for e in entries
            if (subject, e.subgroup, e.chapter_num) in wrong_chapters
        )
        blank = [
            (e.chapter_num, e.chapter_name, e.subgroup)
            for e in entries
            if notes_by_chapter.get((subject, e.subgroup, e.chapter_num), 0) == 0
            and (subject, e.subgroup, e.chapter_num) not in wrong_chapters
        ]
        result[subject] = {
            "total": total,
            "with_notes": with_notes,
            "with_wrongs": with_wrongs,
            "blank_chapters": blank[:10],
            "blank_total": len(blank),
        }
    return result


def _format_chapter_key(key):
    """三元键 (subject, subgroup, chapter_num) → 「数学一·高等数学·第3章」展示串。"""
    if len(key) == 3:
        subject, subgroup, chapter_num = key
    else:  # 兼容旧形态
        subject, chapter_num = key
        subgroup = ""
    parts = [subject]
    if subgroup:
        parts.append(subgroup)
    parts.append(f"第{chapter_num}章")
    return "·".join(parts)


def build_exposure_block(exposure, period_name):
    new_cards = exposure["new_cards"]
    stubborn = exposure["stubborn_cards"]
    chapter_activity = exposure["chapter_activity"]

    if not new_cards and not stubborn and not chapter_activity:
        return f"- 本{period_name}没有新增错题卡或顽固卡需要重点关注。"

    lines = []
    if new_cards:
        subject_counts = {}
        for card in new_cards:
            subject_counts[card["subject"]] = subject_counts.get(card["subject"], 0) + 1
        subj_text = "、".join(
            f"{s} {c} 道" for s, c in sorted(subject_counts.items(), key=lambda x: x[1], reverse=True)
        )
        lines.append(f"- 本{period_name}新增错题 {len(new_cards)} 道（{subj_text}）。")
    else:
        lines.append(f"- 本{period_name}没有记录新增错题。")

    if chapter_activity:
        ranked = sorted(
            chapter_activity.items(),
            key=lambda kv: kv[1]["new"] + kv[1]["fail"],
            reverse=True,
        )[:3]
        items = []
        for key, slot in ranked:
            label = _format_chapter_key(key)
            items.append(f"{label}（新增 {slot['new']} / 复习失败 {slot['fail']}）")
        if items:
            lines.append("- 章节积压 TOP：" + "；".join(items) + "。")

    if stubborn:
        lines.append(f"- 顽固卡 TOP {min(5, len(stubborn))}（周期内仍判「不会」或多次失败）：")
        for card in stubborn[:5]:
            ch_part = f"第{card['chapter_num']}章 " if card['chapter_num'] is not None else ""
            subgroup_part = f"·{card['subgroup']}" if card.get('subgroup') else ""
            lines.append(
                f"  - {card['subject']}{subgroup_part}·{ch_part}{card['topic']}"
                f"（失败 {card['fail_in_range']} 次，最近 {card['latest_day']}）"
            )
    return "\n".join(lines)


def build_cross_signals_block(cross_signals, period_name):
    only_drilling = cross_signals["only_drilling"]
    only_theory = cross_signals["only_theory"]
    healthy = cross_signals["healthy"]

    if not (only_drilling or only_theory or healthy):
        return f"- 本{period_name}笔记与错题数据不足，等数据攒起来再做交叉对照。"

    lines = []
    if only_drilling:
        items = [f"{_format_chapter_key(s['key'])}（错题 {s['wrong']}，笔记 0）" for s in only_drilling[:5]]
        lines.append(f"- ⚠ only-drilling（光刷题没沉淀）：{'；'.join(items)}。建议下{period_name}补一篇套路总结。")
    if only_theory:
        items = [f"{_format_chapter_key(s['key'])}（笔记 {s['notes']}，错题 0）" for s in only_theory[:5]]
        lines.append(f"- ⓘ only-theory（光看理论没验题）：{'；'.join(items)}。建议下{period_name}做几道对应题验收。")
    if healthy:
        items = [f"{_format_chapter_key(s['key'])}（笔记 {s['notes']} / 错题 {s['wrong']}）" for s in healthy[:3]]
        lines.append(f"- ✓ 良性沉淀：{'；'.join(items)}。")
    if not lines:
        lines.append(f"- 本{period_name}交叉信号都正常。")
    return "\n".join(lines)


def build_coverage_block(coverage, period_name):
    if not coverage:
        return f"- 暂无知识地图可对照（请先在 知识地图/ 下建立科目章节表）。"

    lines = []
    for subject, info in coverage.items():
        total = info["total"]
        with_notes = info["with_notes"]
        with_wrongs = info["with_wrongs"]
        pct_notes = (with_notes / total * 100) if total else 0
        pct_wrongs = (with_wrongs / total * 100) if total else 0
        lines.append(
            f"- {subject}：共 {total} 章；笔记覆盖 {with_notes}/{total}（{pct_notes:.0f}%），"
            f"错题覆盖 {with_wrongs}/{total}（{pct_wrongs:.0f}%）。"
        )
        if info["blank_chapters"]:
            def _strip_cn_chapter_prefix(name):
                return re.sub(r"^第[零一二三四五六七八九十百]+章\s*", "", name).strip()
            blank_text = "、".join(
                f"{subgroup}·第{num}章 {_strip_cn_chapter_prefix(name)}".strip("·").strip()
                for num, name, subgroup in info["blank_chapters"][:5]
            )
            extra = ""
            if info["blank_total"] > 5:
                extra = f"（共 {info['blank_total']} 章空白，仅列前 5）"
            lines.append(f"  - 仍空白：{blank_text}{extra}")
    return "\n".join(lines)


def collect_chapter_grill_stats(obsidian_root, start, end):
    root = Path(obsidian_root) / "章节掌握报告" / "408"
    if not root.exists():
        return {
            "count": 0,
            "module_counts": {},
            "mastery_counts": {"不会": 0, "半会": 0, "会": 0},
            "highlights": [],
            "blockers": [],
        }

    module_counts = {}
    mastery_counts = {"不会": 0, "半会": 0, "会": 0}
    highlights = []
    blockers = []

    for md_file in root.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm, body, _ = parse_frontmatter(text)
        session_date = str(fm.get("session_date", "")).strip()
        if not session_date:
            continue
        try:
            report_day = date.fromisoformat(session_date)
        except ValueError:
            continue
        if not (start <= report_day <= end):
            continue
        module = str(fm.get("module", "未标注模块")).strip() or "未标注模块"
        chapter = str(fm.get("chapter", md_file.stem)).strip() or md_file.stem
        mastery = str(fm.get("overall_mastery", "")).strip()
        if mastery in mastery_counts:
            mastery_counts[mastery] += 1
        module_counts[module] = module_counts.get(module, 0) + 1
        highlights.append(f"408 {module}《{chapter}》完成 1 次章节拷打（总体：{mastery or '未标注'}）。")
        blockers.extend(extract_list_items(body, "半会但不稳的点"))
        blockers.extend(extract_list_items(body, "不会或有能力错觉的点"))
        blockers.extend(extract_list_items(body, "关键漏洞"))

    return {
        "count": sum(module_counts.values()),
        "module_counts": module_counts,
        "mastery_counts": mastery_counts,
        "highlights": highlights,
        "blockers": blockers,
    }


def build_chapter_stats(chapter_stats, period_name):
    if chapter_stats["count"] == 0:
        return f"- 本{period_name}没有新的章节拷打报告。"

    module_summary = "、".join(
        f"{module} {count} 章"
        for module, count in sorted(chapter_stats["module_counts"].items(), key=lambda item: item[1], reverse=True)
    )
    blocker_lines = chapter_stats["blockers"][:3]
    lines = [
        f"- 本{period_name}新增 {chapter_stats['count']} 份章节掌握报告。",
        f"- 模块分布：{module_summary}。",
        "总体掌握分布：不会 {不会} / 半会 {半会} / 会 {会}。".format(**chapter_stats["mastery_counts"]),
    ]
    if blocker_lines:
        lines.append("- 章节拷打高频漏洞：" + "；".join(blocker_lines) + "。")
    return "\n".join(lines)


def build_score_summary(score_records, period_name):
    if not score_records:
        return f"- 本{period_name}没有结构化记录训练成绩；后续可在 `/progress` 里补成绩项。", {}

    grouped = {}
    for item in score_records:
        key = (item["subject"], item["kind"])
        grouped.setdefault(key, []).append(item)

    lines = [f"- 本{period_name}共记录 {len(score_records)} 条训练成绩。"]
    subject_counts = {}
    ordered_groups = []

    for key, records in grouped.items():
        records.sort(key=lambda item: (item["date"], item["source"]))
        subject, kind = key
        subject_counts[subject] = subject_counts.get(subject, 0) + len(records)
        first = records[0]
        latest = records[-1]
        best = max(records, key=lambda item: (item["score"] / item["total"], item["score"], item["date"]))
        avg_rate = sum(item["score"] / item["total"] for item in records) / len(records)
        delta = (latest["score"] / latest["total"] - first["score"] / first["total"]) * 100
        ordered_groups.append({
            "subject": subject,
            "kind": kind,
            "count": len(records),
            "first": first,
            "latest": latest,
            "best": best,
            "avg_rate": avg_rate,
            "delta": delta,
        })

    ordered_groups.sort(
        key=lambda item: (item["latest"]["date"], item["count"], item["latest"]["score"] / item["latest"]["total"]),
        reverse=True,
    )

    for item in ordered_groups[:5]:
        latest = item["latest"]
        first = item["first"]
        best = item["best"]
        if item["count"] == 1:
            lines.append(
                "- {subject}·{kind}：1 次，最近 {score}/{total}，完成率 {rate:.1f}%。".format(
                    subject=item["subject"],
                    kind=item["kind"],
                    score=format_number(latest["score"]),
                    total=format_number(latest["total"]),
                    rate=latest["score"] / latest["total"] * 100,
                )
            )
            continue

        delta_text = "持平"
        if abs(item["delta"]) >= 0.05:
            sign = "+" if item["delta"] > 0 else ""
            delta_text = f"{sign}{item['delta']:.1f}pct"
        lines.append(
            "- {subject}·{kind}：{count} 次，首次 {first_score}/{first_total}，最近 {latest_score}/{latest_total}，"
            "最高 {best_score}/{best_total}，平均完成率 {avg_rate:.1f}%（{delta_text}）。".format(
                subject=item["subject"],
                kind=item["kind"],
                count=item["count"],
                first_score=format_number(first["score"]),
                first_total=format_number(first["total"]),
                latest_score=format_number(latest["score"]),
                latest_total=format_number(latest["total"]),
                best_score=format_number(best["score"]),
                best_total=format_number(best["total"]),
                avg_rate=item["avg_rate"] * 100,
                delta_text=delta_text,
            )
        )

    return "\n".join(lines), subject_counts


def render_recap(template, mapping):
    content = template
    for key, value in mapping.items():
        content = content.replace(f"{{{key}}}", value)
    return content + "\n"


def generate_recap(obsidian_root, target_date, period, force=False):
    start, end, label, filename = get_date_range(target_date, period)
    report_dir = Path(obsidian_root) / "复盘报告"
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = report_dir / filename

    if output_path.exists() and not force:
        return None  # 已存在，不重复生成

    period_name = "月" if period == "month" else "周"
    template_name = "月复盘模板.md" if period == "month" else "周复盘模板.md"

    highlights, blockers, logged_days, total_hours, score_records = collect_logs(obsidian_root, start, end)
    chapter_stats = collect_chapter_grill_stats(obsidian_root, start, end)
    highlights = highlights + chapter_stats["highlights"]
    blockers = blockers + chapter_stats["blockers"]
    score_records = merge_score_records(score_records, collect_archive_subject_scores(obsidian_root, start, end))
    total_reviews, status_counts, subject_counts = collect_review_stats(obsidian_root, start, end)
    score_stats, score_subject_counts = build_score_summary(score_records, period_name)
    subject_signal = infer_subject_mentions(highlights + blockers)
    score_subject_counts["408"] = score_subject_counts.get("408", 0) + chapter_stats["count"]
    combined = {
        s: subject_counts[s] + subject_signal.get(s, 0) + score_subject_counts.get(s, 0)
        for s in PLAN_SUBJECTS
    }
    active_subjects = [s for s, c in sorted(combined.items(), key=lambda x: x[1], reverse=True) if c > 0]
    active_subjects_text = "、".join(active_subjects[:3]) if active_subjects else "记录不足"

    period_notes = scan_notes_in_range(Path(obsidian_root), start, end)
    note_stats_block = render_recap_notes_block(period_notes, period_name)
    wrong_exposure = collect_wrong_exposure(obsidian_root, start, end)
    exposure_stats_block = build_exposure_block(wrong_exposure, period_name)
    cross_signals = collect_cross_signals(period_notes, wrong_exposure)
    cross_signals_block = build_cross_signals_block(cross_signals, period_name)

    coverage_block = ""
    coverage = {}
    if period == "month":
        coverage = collect_coverage(obsidian_root)
        coverage_block = build_coverage_block(coverage, period_name)

    review_stats = build_bullets([
        f"本{period_name}共记录 {total_reviews} 次复习更新。",
        f"状态分布：不会 {status_counts['不会']} / 半会 {status_counts['半会']} / 会 {status_counts['会']}。",
        "涉及科目：" + ("、".join(f"{s} {subject_counts[s]} 次" for s in PLAN_SUBJECTS if subject_counts[s]) or "暂无。"),
    ], f"- 本{period_name}暂未检索到复习更新。")

    next_actions = []
    if cross_signals["only_drilling"]:
        first = cross_signals["only_drilling"][0]
        next_actions.append(f"给 {_format_chapter_key(first['key'])} 补一篇套路总结，结束 only-drilling。")
    if cross_signals["only_theory"]:
        first = cross_signals["only_theory"][0]
        next_actions.append(f"为 {_format_chapter_key(first['key'])} 的笔记做几道题验收。")
    if blockers:
        next_actions.append(f"优先拆解：{blockers[0]}")
    if active_subjects:
        next_actions.append(f"下{period_name}继续给 {active_subjects[0]} 留整块时间。")
    if total_reviews == 0:
        next_actions.append("把 `/review` 固定到常规节奏，避免旧题积压。")
    else:
        next_actions.append("保留检查点，及时把新卡点写回错题本或知识地图。")

    mapping = {
        "period_label": label,
        "period_range": f"{start.isoformat()} ~ {end.isoformat()}",
        "logged_days": str(logged_days),
        "total_hours": recap_hours(total_hours),
        "active_subjects": active_subjects_text,
        "highlights": build_bullets(highlights, f"- 本{period_name}日志产出较少，优先补齐关键学习记录。"),
        "chapter_stats": build_chapter_stats(chapter_stats, period_name),
        "score_stats": score_stats,
        "review_stats": review_stats,
        "note_stats": note_stats_block,
        "exposure_stats": exposure_stats_block,
        "cross_signals": cross_signals_block,
        "blockers": build_bullets(blockers, f"- 本{period_name}未显式记录卡点，建议把卡点写得更具体。"),
        "next_actions": build_bullets(next_actions, f"- 下{period_name}先保证日志和复盘的连续性。"),
    }
    if period == "month":
        mapping["coverage_stats"] = coverage_block

    content = render_recap(load_template_markdown(template_name), mapping)

    atomic_write(output_path, content)

    return {
        "path": str(output_path),
        "period": period,
        "label": label,
        "date_range": f"{start.isoformat()} ~ {end.isoformat()}",
        "logged_days": logged_days,
        "total_hours": round(total_hours, 2),
        "review_count": total_reviews,
        "score_count": len(score_records),
        "note_count": len(period_notes),
        "new_wrong_count": len(wrong_exposure["new_cards"]),
        "stubborn_count": len(wrong_exposure["stubborn_cards"]),
        "only_drilling_count": len(cross_signals["only_drilling"]),
        "only_theory_count": len(cross_signals["only_theory"]),
    }


def main():
    parser = argparse.ArgumentParser(description="生成周/月复盘")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("--period", choices=["week", "month"], default="week", help="复盘周期（默认 week）")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    args = parser.parse_args()

    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    today = parse_today(args.today)
    
    # 自动补齐上一周期的复盘（不强制覆盖已有的）
    if args.period == "month":
        # 找上个月某一天
        first_day_of_this_month = today.replace(day=1)
        prev_target_date = first_day_of_this_month - timedelta(days=1)
    else:
        # 找上周某一天
        monday = today - timedelta(days=today.weekday())
        prev_target_date = monday - timedelta(days=1)
        
    prev_result = generate_recap(obsidian_root, prev_target_date, args.period, force=False)
    
    # 生成当前周期的复盘（强制覆盖更新）
    current_result = generate_recap(obsidian_root, today, args.period, force=True)

    out = dict(current_result or {})
    out["backfilled"] = prev_result

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
