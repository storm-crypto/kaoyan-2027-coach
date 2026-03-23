"""学习者档案读写辅助函数。"""
import re
from pathlib import Path

from env_util import resolve_skill_root


def extract_section_block(text, heading):
    pattern = rf"^\s*## {re.escape(heading)}\n(.*?)(?=^\s*## |\Z)"
    match = re.search(pattern, text, re.M | re.S)
    return match.group(1).strip("\n") if match else ""


def extract_list_items(text, heading):
    block = extract_section_block(text, heading)
    items = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            value = stripped[2:].strip()
        else:
            match = re.match(r"^\d+\.\s*(.*)$", stripped)
            value = match.group(1).strip() if match else ""
        if value:
            items.append(value)
    return items


def parse_daily_hours(text, default=None):
    match = re.search(r"每日可投入时长\*\*[:：]\s*([0-9]+(?:\.[0-9]+)?)", text)
    if match:
        return float(match.group(1))
    return default


def parse_subject_targets(text):
    block = extract_section_block(text, "各科当前状态")
    rows = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
        if len(cells) != 5 or cells[0] == "科目" or set(cells[0]) == {"-"}:
            continue
        target_cell = cells[2]
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", target_cell)
        rows[cells[0]] = float(match.group(1)) if match else None
    return rows


def parse_mock_rows(text):
    block = extract_section_block(text, "模考成绩追踪")
    rows = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
        if len(cells) != 7 or cells[0] in {"日期", "------"} or set(cells[0]) == {"-"}:
            continue
        rows.append({
            "date": cells[0],
            "政治": cells[1],
            "数学一": cells[2],
            "英语一": cells[3],
            "408": cells[4],
            "总分": cells[5],
            "备注": cells[6],
        })
    return rows


def parse_score_cell(value):
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", value or "")
    return float(match.group(1)) if match else None


def append_mock_row(text, row):
    return upsert_mock_row(text, row)


def upsert_mock_row(text, row):
    marker = "## 模考成绩追踪"
    section_start = text.find(marker)
    if section_start == -1:
        raise ValueError("档案中缺少“模考成绩追踪”区块")

    next_section = text.find("\n## ", section_start + len(marker))
    if next_section == -1:
        next_section = len(text)

    section = text[section_start:next_section].rstrip("\n")
    row_line = (
        f"| {row['date']} | {row['政治']} | {row['数学一']} | {row['英语一']} | "
        f"{row['408']} | {row['总分']} | {row['备注']} |"
    )
    section_lines = section.splitlines()
    updated_lines = []
    replaced = False
    for line in section_lines:
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
            if len(cells) == 7 and cells[0] == row["date"]:
                if not replaced:
                    updated_lines.append(row_line)
                    replaced = True
                continue
        updated_lines.append(line)

    if not replaced:
        updated_lines.append(row_line)

    updated_section = "\n".join(updated_lines).rstrip("\n") + "\n"
    return text[:section_start] + updated_section + text[next_section:]


def infer_subject_mentions(items):
    mapping = {
        "数学一": ("数学", "高数", "线代", "概率"),
        "408": ("408", "数据结构", "组成原理", "操作系统", "计算机网络"),
        "英语一": ("英语", "阅读", "翻译", "写作", "完形"),
        "政治": ("政治", "马原", "毛中特", "史纲", "思修", "时政"),
    }
    counts = {subject: 0 for subject in mapping}
    for item in items:
        for subject, keywords in mapping.items():
            if any(keyword in item for keyword in keywords):
                counts[subject] += 1
    return counts


def load_archive_text(obsidian_root):
    archive_path = Path(obsidian_root) / "我的学习者档案.md"
    if not archive_path.exists():
        raise FileNotFoundError(f"档案不存在: {archive_path}")
    return archive_path, archive_path.read_text(encoding="utf-8")


def load_template_markdown(template_name):
    template_path = resolve_skill_root() / "templates" / template_name
    text = template_path.read_text(encoding="utf-8")
    match = re.search(r"```markdown\n(.*?)\n```", text, re.S)
    return match.group(1) if match else text
