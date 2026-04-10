#!/usr/bin/env python3
"""导入 Gemini Voyager 聊天记录，生成 408 章节掌握报告并回写知识地图。"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from archive_ops import load_template_markdown
from env_util import atomic_write, json_error, resolve_obsidian_root

STRUCTURED_SECTIONS = (
    "章节信息",
    "本章结论",
    "已掌握",
    "半会但不稳",
    "不会或有能力错觉",
    "关键漏洞",
    "下一步复习动作",
    "可映射考点",
)
SECTION_RE = re.compile(r"^【([^】]+)】\s*$", re.M)
MASTERY_VALUES = {"会", "半会", "不会"}
MODULE_ALIASES = {
    "数据结构": "数据结构",
    "计组": "计算机组成原理",
    "组成原理": "计算机组成原理",
    "计算机组成原理": "计算机组成原理",
    "操作系统": "操作系统",
    "计算机网络": "计算机网络",
    "计网": "计算机网络",
}
MODULE_PATTERNS = (
    ("计算机组成原理", ("计算机组成原理", "计组", "组成原理")),
    ("操作系统", ("操作系统",)),
    ("计算机网络", ("计算机网络", "计网")),
    ("数据结构", ("数据结构",)),
)


def parse_args() -> Tuple[Optional[str], str, Optional[str]]:
    raw_args = sys.argv[1:]
    obsidian_root_arg = None
    voyager_json_path = None

    if raw_args and not raw_args[0].startswith("--"):
        if len(raw_args) >= 2 and not raw_args[1].startswith("--"):
            obsidian_root_arg = raw_args[0]
            voyager_json_path = raw_args[1]
            raw_args = raw_args[2:]
        else:
            voyager_json_path = raw_args[0]
            raw_args = raw_args[1:]

    parser = argparse.ArgumentParser(description="导入 Gemini Voyager 聊天记录，生成章节掌握报告")
    parser.add_argument("--today", help="导入日期 YYYY-MM-DD；默认取导出时间的日期")
    args = parser.parse_args(raw_args)

    if not voyager_json_path:
        json_error("缺少 Voyager JSON 路径：用法 python3 scripts/import_chapter_grill.py [$OBSIDIAN_ROOT] [voyager_json_path] [--today YYYY-MM-DD]")
    return obsidian_root_arg, voyager_json_path, args.today


def parse_export_date(today_arg: Optional[str], exported_at: Optional[str]) -> str:
    if today_arg:
        return today_arg
    if exported_at:
        normalized = exported_at.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).date().isoformat()
        except ValueError:
            pass
    return datetime.today().date().isoformat()


def load_voyager_payload(path: Path) -> Dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        json_error(f"Voyager JSON 不存在: {path}")
    except json.JSONDecodeError as exc:
        json_error(f"Voyager JSON 解析失败: {exc}")

    if payload.get("format") != "gemini-voyager.chat.v1":
        json_error("只支持 format = gemini-voyager.chat.v1 的 Voyager 导出文件")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        json_error("Voyager 导出文件缺少有效的 items 对话数组")
    return payload


def normalize_module_name(text: str) -> str:
    value = re.sub(r"[\(\（].*?[\)\）]", "", (text or "")).strip()
    for alias, canonical in MODULE_ALIASES.items():
        if alias in value:
            return canonical
    return value


def normalize_topic(text: str) -> str:
    value = (text or "").strip()
    value = re.sub(r"^\d+(?:\.\d+)?\s*", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def slugify(text: str) -> str:
    value = (text or "").strip()
    value = re.sub(r"\s+", "-", value)
    value = value.replace("/", "-")
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "未命名章节"


def extract_sections(text: str) -> Dict[str, str]:
    matches = list(SECTION_RE.finditer(text))
    sections: Dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1).strip()] = text[start:end].strip()
    return sections


def parse_list_section(text: str) -> List[str]:
    items = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            value = stripped[2:].strip()
            if value:
                items.append(value)
    return items


def parse_keyed_bullets(text: str) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for item in parse_list_section(text):
        if "：" in item:
            key, value = item.split("：", 1)
        elif ":" in item:
            key, value = item.split(":", 1)
        else:
            continue
        data[key.strip()] = value.strip()
    return data


def parse_mapping_items(text: str) -> List[Dict[str, str]]:
    items = []
    for line in parse_list_section(text):
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3:
            continue
        topic, mastery, evidence = parts
        if mastery not in MASTERY_VALUES:
            continue
        items.append({
            "topic": topic,
            "mastery": mastery,
            "evidence": evidence,
        })
    return items


def parse_structured_summary(text: str) -> Optional[Dict[str, object]]:
    sections = extract_sections(text)
    if not all(section in sections for section in STRUCTURED_SECTIONS):
        return None

    chapter_info = parse_keyed_bullets(sections["章节信息"])
    conclusion = parse_keyed_bullets(sections["本章结论"])
    next_actions = parse_keyed_bullets(sections["下一步复习动作"])
    mappings = parse_mapping_items(sections["可映射考点"])

    subject = chapter_info.get("科目", "").strip()
    if subject != "408":
        json_error(f"/chapter_grill_import v1 只支持 408，当前科目为: {subject or '未填写'}")

    overall_mastery = conclusion.get("总体掌握", "").strip()
    if overall_mastery not in MASTERY_VALUES:
        json_error("固定总评块中的“总体掌握”必须是 会/半会/不会")

    return {
        "subject": subject,
        "module": normalize_module_name(chapter_info.get("模块", "")) or "未标注模块",
        "chapter": chapter_info.get("章节", "").strip() or "未标注章节",
        "materials": [chapter_info.get("资料来源", "").strip()] if chapter_info.get("资料来源", "").strip() else [],
        "overall_mastery": overall_mastery,
        "one_liner": conclusion.get("一句话结论", "").strip() or "本章已完成结构化总评。",
        "mastered": parse_list_section(sections["已掌握"]),
        "unstable": parse_list_section(sections["半会但不稳"]),
        "illusions": parse_list_section(sections["不会或有能力错觉"]),
        "critical_gaps": parse_list_section(sections["关键漏洞"]),
        "next_actions": {
            "24小时内": next_actions.get("24小时内", "").strip(),
            "3天内": next_actions.get("3天内", "").strip(),
            "下次开始前": next_actions.get("下次开始前", "").strip(),
        },
        "mapping_items": mappings,
    }


def find_structured_summary(items: Sequence[Dict[str, str]]) -> Optional[Dict[str, object]]:
    for item in reversed(items):
        summary = parse_structured_summary(item.get("assistant", ""))
        if summary:
            return summary
    return None


def collect_evidence_quotes(items: Sequence[Dict[str, str]], limit: int = 6) -> List[str]:
    evidence: List[str] = []
    wanted = ("判卷结论", "漏洞定位", "追问", "纠偏方向")
    for item in items:
        sections = extract_sections(item.get("assistant", ""))
        for key in wanted:
            if key not in sections:
                continue
            lines = parse_list_section(sections[key])
            if lines:
                for line in lines[:2]:
                    evidence.append(f"{key}：{line}")
            else:
                compact = " ".join(line.strip() for line in sections[key].splitlines() if line.strip())
                if compact:
                    evidence.append(f"{key}：{compact}")
            if len(evidence) >= limit:
                return evidence[:limit]
    return evidence[:limit]


def infer_module_from_text(text: str) -> str:
    scores: Dict[str, int] = {canonical: 0 for canonical, _ in MODULE_PATTERNS}
    for canonical, keywords in MODULE_PATTERNS:
        for keyword in keywords:
            scores[canonical] += text.count(keyword)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "未标注模块"


def infer_chapter_from_text(text: str) -> str:
    patterns = [
        r"(第[一二三四五六七八九十0-9]+章[^\n，。]*)",
        r"((?:0[1-9]|1[0-9])\s+[^\n，。]{2,20})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            chapter = match.group(1).strip()
            chapter = chapter.replace("第一章", "第1章").replace("第二章", "第2章").replace("第三章", "第3章")
            chapter = chapter.replace("第四章", "第4章").replace("第五章", "第5章").replace("第六章", "第6章")
            chapter = chapter.replace("第七章", "第7章").replace("第八章", "第8章").replace("第九章", "第9章")
            chapter = chapter.replace("第十章", "第10章")
            return chapter
    return "未标注章节"


def infer_overall_mastery(text: str) -> str:
    for mastery in ("不会", "半会", "会"):
        if mastery in text:
            return mastery
    return "半会"


def build_fallback_summary(payload: Dict[str, object], items: Sequence[Dict[str, str]]) -> Dict[str, object]:
    title = str(payload.get("title", "") or "")
    transcript_text = "\n".join(
        part
        for item in items
        for part in (item.get("user", ""), item.get("assistant", ""))
        if part
    )
    module = infer_module_from_text("\n".join([title, transcript_text]))
    chapter = infer_chapter_from_text(transcript_text)
    evidence = collect_evidence_quotes(items, limit=6)
    critical_gaps = [
        line for line in evidence
        if "漏洞定位" in line or "判卷结论" in line
    ][:4]
    if not critical_gaps:
        critical_gaps = ["未检测到固定总评块；本次按完整聊天记录做弱结构化导入。"]
    return {
        "subject": "408",
        "module": module,
        "chapter": chapter,
        "materials": [],
        "overall_mastery": infer_overall_mastery(transcript_text),
        "one_liner": "未检测到固定总评块；本次按完整聊天记录做弱结构化导入，建议下次在 Gemini 里补一句“结束本章，按模板总评”。",
        "mastered": ["未检测到固定“已掌握”区块，建议下次让 Gemini 在收尾时显式总结。"] if not evidence else evidence[:2],
        "unstable": ["本次导入缺少结构化收尾，半会与不会的边界需要你下次通过固定总评补清。"] if len(evidence) < 3 else evidence[2:4],
        "illusions": ["如果一轮对话里反复出现追问，说明这一块仍有能力错觉。"],
        "critical_gaps": critical_gaps,
        "next_actions": {
            "24小时内": "回看这章里被连续追问的那一个点，并尝试脱稿复述。",
            "3天内": "补一次固定总评版章节拷打，避免后续知识地图只能弱更新。",
            "下次开始前": "在 Gemini 结束时加一句“结束本章，按模板总评”。",
        },
        "mapping_items": [],
    }


def render_bullets(items: Sequence[str], fallback: str) -> str:
    if not items:
        return f"- {fallback}"
    return "\n".join(f"- {item}" for item in items)


def parse_knowledge_map_rows(path: Path) -> Tuple[List[str], List[Dict[str, object]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    rows: List[Dict[str, object]] = []
    current_module = ""
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## "):
            current_module = normalize_module_name(stripped[3:].strip())
            continue
        if "|" not in line:
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) != 4:
            continue
        topic_cell = cells[0]
        if not topic_cell or topic_cell == "考点" or set(topic_cell) == {"-"}:
            continue
        if topic_cell.startswith("**") and topic_cell.endswith("**"):
            continue
        rows.append({
            "line_index": index,
            "module": current_module,
            "topic": normalize_topic(topic_cell),
            "cells": cells,
        })
    return lines, rows


def topic_tokens(text: str) -> List[str]:
    normalized = normalize_topic(text)
    parts = re.split(r"[\s/\-（）()、，,]+", normalized)
    return [part for part in parts if part]


def match_knowledge_row(rows: Sequence[Dict[str, object]], module: str, target_topic: str) -> Tuple[Optional[Dict[str, object]], str]:
    target_module = normalize_module_name(module)
    target_norm = normalize_topic(target_topic)
    module_rows = [row for row in rows if row["module"] == target_module]
    if not module_rows:
        return None, f"模块“{target_module}”下没有可匹配的叶子考点"

    exact = [row for row in module_rows if row["topic"] == target_norm]
    if len(exact) == 1:
        return exact[0], ""
    if len(exact) > 1:
        return None, "精确匹配到了多行候选"

    contains = [row for row in module_rows if target_norm and (target_norm in row["topic"] or row["topic"] in target_norm)]
    if len(contains) == 1:
        return contains[0], ""
    if len(contains) > 1:
        return None, "近似匹配到了多行候选"

    target_token_set = set(topic_tokens(target_norm))
    scored = []
    for row in module_rows:
        row_tokens = set(topic_tokens(str(row["topic"])))
        overlap = len(target_token_set & row_tokens)
        if overlap > 0:
            scored.append((overlap, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return None, "未找到匹配考点"
    if len(scored) == 1 or scored[0][0] > scored[1][0]:
        return scored[0][1], ""
    return None, "近似匹配分数并列，无法安全回写"


def update_knowledge_map(
    obsidian_root: Path,
    module: str,
    session_date: str,
    mapping_items: Sequence[Dict[str, str]],
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    if not mapping_items:
        return [], []

    map_path = obsidian_root / "知识地图" / "408.md"
    if not map_path.exists():
        return [], [{
            "topic": item["topic"],
            "mastery": item["mastery"],
            "reason": f"知识地图不存在: {map_path}",
        } for item in mapping_items]

    lines, rows = parse_knowledge_map_rows(map_path)
    updated: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []

    for item in mapping_items:
        row, reason = match_knowledge_row(rows, module, item["topic"])
        if row is None:
            skipped.append({
                "topic": item["topic"],
                "mastery": item["mastery"],
                "reason": reason,
            })
            continue
        cells = list(row["cells"])
        cells[1] = item["mastery"]
        note = f"章节拷打 {session_date}：{item['evidence']}"
        cells[3] = note[:40]
        lines[row["line_index"]] = "| " + " | ".join(cells) + " |"
        updated.append({
            "topic": item["topic"],
            "mastery": item["mastery"],
            "matched_topic": str(row["topic"]),
        })

    atomic_write(map_path, "\n".join(lines) + "\n")
    return updated, skipped


def render_action_section(next_actions: Dict[str, str]) -> str:
    items = [
        ("24小时内", next_actions.get("24小时内", "").strip()),
        ("3天内", next_actions.get("3天内", "").strip()),
        ("下次开始前", next_actions.get("下次开始前", "").strip()),
    ]
    lines = []
    for key, value in items:
        lines.append(f"- **{key}**：{value or '未明确给出，建议围绕本章最薄弱点补一次脱稿复述。'}")
    return "\n".join(lines)


def render_map_results(updated: Sequence[Dict[str, str]], skipped: Sequence[Dict[str, str]]) -> str:
    lines: List[str] = []
    if updated:
        lines.append("- 已回写：")
        for item in updated:
            lines.append(f"  - {item['topic']} → {item['mastery']}（匹配到 {item['matched_topic']}）")
    else:
        lines.append("- 已回写：无")
    if skipped:
        lines.append("- 未回写：")
        for item in skipped:
            lines.append(f"  - {item['topic']} → {item['mastery']}（{item['reason']}）")
    else:
        lines.append("- 未回写：无")
    return "\n".join(lines)


def build_report_content(
    summary: Dict[str, object],
    session_date: str,
    import_confidence: str,
    evidence_quotes: Sequence[str],
    updated: Sequence[Dict[str, str]],
    skipped: Sequence[Dict[str, str]],
) -> str:
    template = load_template_markdown("章节掌握报告模板.md")
    replacements = {
        "subject": str(summary["subject"]),
        "module": str(summary["module"]),
        "chapter": str(summary["chapter"]),
        "session_date": session_date,
        "import_confidence": import_confidence,
        "overall_mastery": str(summary["overall_mastery"]),
        "knowledge_map_updated": str(len(updated)),
        "knowledge_map_skipped": str(len(skipped)),
        "materials": " / ".join(summary["materials"]) if summary["materials"] else "未标注",
        "one_liner": str(summary["one_liner"]),
        "mastered": render_bullets(summary["mastered"], "本次没有显式总结“已掌握”项。"),
        "unstable": render_bullets(summary["unstable"], "本次没有显式总结“半会但不稳”项。"),
        "illusions": render_bullets(summary["illusions"], "本次没有显式总结“不会或有能力错觉”项。"),
        "gaps": render_bullets(summary["critical_gaps"], "本次没有显式总结“关键漏洞”项。"),
        "evidence": render_bullets(evidence_quotes, "本次导入没有抽取到标准化判卷片段。"),
        "actions": render_action_section(summary["next_actions"]),
        "knowledge_map_results": render_map_results(updated, skipped),
    }
    for key, value in replacements.items():
        template = template.replace(f"{{{key}}}", value)
    return template + "\n"


def pick_output_path(obsidian_root: Path, module: str, session_date: str, chapter: str) -> Path:
    base_dir = obsidian_root / "章节掌握报告" / "408" / module
    base_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(chapter)
    candidate = base_dir / f"{session_date}-{slug}.md"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        alt = base_dir / f"{session_date}-{slug}-{index:02d}.md"
        if not alt.exists():
            return alt
        index += 1


def main() -> None:
    obsidian_root_arg, voyager_json_path, today_arg = parse_args()
    obsidian_root = resolve_obsidian_root(obsidian_root_arg)
    payload = load_voyager_payload(Path(voyager_json_path))
    items = payload["items"]
    session_date = parse_export_date(today_arg, str(payload.get("exportedAt", "") or ""))

    structured = find_structured_summary(items)
    if structured:
        summary = structured
        import_confidence = "high"
    else:
        summary = build_fallback_summary(payload, items)
        import_confidence = "low"

    evidence_quotes = collect_evidence_quotes(items)
    updated, skipped = update_knowledge_map(
        obsidian_root,
        str(summary["module"]),
        session_date,
        summary["mapping_items"],
    )
    content = build_report_content(summary, session_date, import_confidence, evidence_quotes, updated, skipped)
    output_path = pick_output_path(obsidian_root, str(summary["module"]), session_date, str(summary["chapter"]))
    atomic_write(output_path, content)

    print(json.dumps({
        "date": session_date,
        "subject": summary["subject"],
        "module": summary["module"],
        "chapter": summary["chapter"],
        "overall_mastery": summary["overall_mastery"],
        "import_confidence": import_confidence,
        "report_path": str(output_path),
        "knowledge_map_updated": updated,
        "knowledge_map_skipped": skipped,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
