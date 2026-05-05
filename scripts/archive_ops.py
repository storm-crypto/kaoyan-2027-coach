"""学习者档案读写辅助函数。"""
import re
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Pattern, Sequence, Tuple

from env_util import atomic_write, resolve_skill_root


MARKDOWN_TEMPLATE_RE = re.compile(r"```markdown\r?\n(.*?)\r?\n```", re.S)

SUBJECT_SCORE_SECTION_CONFIG = {
    "数学一": {
        "heading": "数学一模拟成绩追踪",
        "columns": ("date", "paper_type", "paper", "total", "issues", "note"),
        "headers": ("日期", "卷型", "卷子", "总分", "主要问题", "备注"),
        "separator": "|------|------|------|------|----------|------|",
        "blank": "| | | | | | |",
    },
    "408": {
        "heading": "408模拟成绩追踪",
        "columns": ("date", "paper_type", "paper", "ds", "co", "os", "cn", "total", "issues", "note"),
        "headers": ("日期", "卷型", "卷子", "DS", "CO", "OS", "CN", "总分", "主要问题", "备注"),
        "separator": "|------|------|------|----|----|----|----|------|----------|------|",
        "blank": "| | | | | | | | | | |",
    },
    "英语一": {
        "heading": "英语一模拟成绩追踪",
        "columns": ("date", "paper_type", "paper", "total", "issues", "note"),
        "headers": ("日期", "卷型", "卷子", "总分", "主要问题", "备注"),
        "separator": "|------|------|------|------|----------|------|",
        "blank": "| | | | | | |",
    },
    "政治": {
        "heading": "政治模拟成绩追踪",
        "columns": ("date", "paper_type", "paper", "total", "issues", "note"),
        "headers": ("日期", "卷型", "卷子", "总分", "主要问题", "备注"),
        "separator": "|------|------|------|------|----------|------|",
        "blank": "| | | | | | |",
    },
}


def _heading_block_pattern(heading: str, level: int) -> Pattern[str]:
    hashes = "#" * level
    return re.compile(
        rf"(^[ \t]{{0,3}}{re.escape(hashes)} {re.escape(heading)}\r?\n)(.*?)(?=^[ \t]{{0,3}}{re.escape(hashes)} |\Z)",
        re.M | re.S,
    )


def extract_heading_block(text: str, heading: str, level: int = 2) -> str:
    match = _heading_block_pattern(heading, level).search(text)
    return match.group(2).strip("\r\n") if match else ""


def replace_heading_block(
    text: str,
    heading: str,
    new_body: str,
    level: int = 2,
    required: bool = True,
) -> str:
    match = _heading_block_pattern(heading, level).search(text)
    if not match:
        if required:
            raise ValueError(f"档案中缺少区块：{heading}")
        return text
    prefix = text[:match.start(2)]
    suffix = text[match.end(2):]
    normalized_body = new_body.strip("\n") + "\n"
    next_heading = "\n" + "#" * level + " "
    if suffix.startswith(next_heading):
        return prefix + normalized_body + suffix
    return prefix + normalized_body + suffix.lstrip("\n")


def extract_section_block(text: str, heading: str) -> str:
    return extract_heading_block(text, heading, level=2)


def extract_list_items(text: str, heading: str) -> List[str]:
    block = extract_heading_block(text, heading, level=2)
    items: List[str] = []
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


def parse_daily_hours(text: str, default: Optional[float] = None) -> Optional[float]:
    match = re.search(r"每日可投入时长\*\*[:：]\s*([0-9]+(?:\.[0-9]+)?)", text)
    if match:
        return float(match.group(1))
    return default


def parse_subject_targets(text: str) -> Dict[str, Optional[float]]:
    block = extract_section_block(text, "各科当前状态")
    rows: Dict[str, Optional[float]] = {}
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


def parse_mock_rows(text: str) -> List[Dict[str, str]]:
    block = extract_section_block(text, "模考成绩追踪")
    rows: List[Dict[str, str]] = []
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


def parse_score_cell(value: str) -> Optional[float]:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", value or "")
    return float(match.group(1)) if match else None


def format_number(value: float) -> str:
    if abs(value - int(value)) < 1e-9:
        return str(int(value))
    return f"{value:.1f}"


def update_archive_date(text: str, day: str) -> str:
    pattern = r"(- \*\*最近更新日期\*\*：)(.*)"
    if not re.search(pattern, text):
        return text
    return re.sub(pattern, rf"\g<1>{day}", text, count=1)


def append_mock_row(text: str, row: Mapping[str, str]) -> str:
    return upsert_mock_row(text, row)


def upsert_mock_row(text: str, row: Mapping[str, str]) -> str:
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


def render_subject_score_section(subject: str) -> str:
    config = SUBJECT_SCORE_SECTION_CONFIG[subject]
    header_row = f"| {' | '.join(config['headers'])} |"
    return "\n".join([
        f"## {config['heading']}",
        header_row,
        config["separator"],
        config["blank"],
    ])


def ensure_subject_score_sections(text: str) -> str:
    missing = [
        render_subject_score_section(subject)
        for subject, config in SUBJECT_SCORE_SECTION_CONFIG.items()
        if f"## {config['heading']}" not in text
    ]
    if not missing:
        return text

    marker = "## 最近聚焦问题（只保留 3-5 条）"
    insertion = "\n\n".join(missing).strip()
    index = text.find(marker)
    if index == -1:
        return text.rstrip("\n") + "\n\n" + insertion + "\n"
    return text[:index].rstrip("\n") + "\n\n" + insertion + "\n\n" + text[index:]


def parse_subject_score_rows(text: str, subject: str) -> List[Dict[str, str]]:
    if subject not in SUBJECT_SCORE_SECTION_CONFIG:
        raise ValueError(f"不支持的单科成绩表: {subject}")
    config = SUBJECT_SCORE_SECTION_CONFIG[subject]
    block = extract_section_block(text, config["heading"])
    rows: List[Dict[str, str]] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
        if cells[0] in {"日期", "------"} or set("".join(cells)) <= {"-", " "}:
            continue
        normalized: Dict[str, str]
        if subject == "数学一" and len(cells) == 5:
            # 旧版数学一表：paper_type 内嵌在 paper 名里。运行 migrate_archive_schemas
            # 之后所有档案都会升级到 6 列；本分支仅作为安全网。
            normalized = {
                "date": cells[0],
                "paper_type": "真题" if "真题" in cells[1] else "模拟",
                "paper": cells[1],
                "total": cells[2],
                "issues": cells[3],
                "note": cells[4],
            }
        elif len(cells) == len(config["columns"]):
            normalized = dict(zip(config["columns"], cells))
        else:
            continue
        if not normalized["date"] or not normalized["paper"]:
            continue
        rows.append(normalized)
    return rows


def upsert_subject_score_row(text: str, subject: str, row: Mapping[str, str]) -> str:
    if subject not in SUBJECT_SCORE_SECTION_CONFIG:
        raise ValueError(f"不支持的单科成绩表: {subject}")
    config = SUBJECT_SCORE_SECTION_CONFIG[subject]
    text = ensure_subject_score_sections(text)
    marker = f"## {config['heading']}"
    section_start = text.find(marker)
    if section_start == -1:
        raise ValueError(f"档案中缺少“{config['heading']}”区块")

    next_section = text.find("\n## ", section_start + len(marker))
    if next_section == -1:
        next_section = len(text)

    section = text[section_start:next_section].rstrip("\n")
    row_line = "| " + " | ".join(row.get(column, "") for column in config["columns"]) + " |"
    section_lines = section.splitlines()
    updated_lines = []
    replaced = False
    for line in section_lines:
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.split("|")[1:-1]]
            existing_date = cells[0] if cells else ""
            existing_paper = ""
            existing_paper_type = ""
            if subject == "数学一" and len(cells) == 5:
                # 旧版数学一表的 in-place upsert,paper_type 从 paper 名推断。
                existing_paper = cells[1]
                existing_paper_type = "真题" if "真题" in cells[1] else "模拟"
            elif len(cells) == len(config["columns"]):
                existing_paper_type = cells[1]
                existing_paper = cells[2]
            if (
                existing_date == row["date"]
                and existing_paper == row["paper"]
                and (not existing_paper_type or existing_paper_type == row.get("paper_type", existing_paper_type))
            ):
                if not replaced:
                    updated_lines.append(row_line)
                    replaced = True
                continue
        updated_lines.append(line)

    if not replaced:
        updated_lines.append(row_line)

    updated_section = "\n".join(updated_lines).rstrip("\n") + "\n"
    return text[:section_start] + updated_section + text[next_section:]


def infer_subject_mentions(items: Sequence[str]) -> Dict[str, int]:
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


def load_archive_text(obsidian_root: Path) -> Tuple[Path, str]:
    archive_path = Path(obsidian_root) / "我的学习者档案.md"
    if not archive_path.exists():
        raise FileNotFoundError(f"档案不存在: {archive_path}")
    raw_text = archive_path.read_text(encoding="utf-8")
    migrated = migrate_archive_schemas(raw_text)
    if migrated != raw_text:
        atomic_write(archive_path, migrated)
    return archive_path, migrated


def safe_load_archive_text(obsidian_root: Path) -> Tuple[Path, str]:
    """读档案,缺失则返回空文本(不写盘),存在则触发迁移。供只读调用方使用。"""
    archive_path = Path(obsidian_root) / "我的学习者档案.md"
    if not archive_path.exists():
        return archive_path, ""
    return load_archive_text(obsidian_root)


def load_template_markdown(template_name: str) -> str:
    template_path = resolve_skill_root() / "templates" / template_name
    text = template_path.read_text(encoding="utf-8")
    match = MARKDOWN_TEMPLATE_RE.search(text)
    if not match:
        raise ValueError(f"模板缺少 ```markdown fenced block: {template_path}")
    return match.group(1)


# ---------------------------------------------------------------------------
# Archive schema migration
# ---------------------------------------------------------------------------

def _is_separator_row(cells: Sequence[str]) -> bool:
    """识别 Markdown 表格的分隔行: 每个 cell 由若干 - / : 构成。"""
    return bool(cells) and all(set(cell) <= {"-", ":", " "} and cell.strip() for cell in cells)


def _is_blank_row(cells: Sequence[str]) -> bool:
    return all(not cell.strip() for cell in cells)


def _migrate_408_table(text: str) -> str:
    """把 408 模拟成绩追踪表的旧格式(6 列 / 9 列)统一升级到当前 10 列 schema。

    历史 schema:
    - 9 列: date | paper(含真题/模拟) | DS | CO | OS | CN | total | issues | note
    - 6 列: date | paper_type | paper | total | issues | note
    - 10 列(当前): date | paper_type | paper | DS | CO | OS | CN | total | issues | note

    幂等:已是 10 列的不动。
    """
    config = SUBJECT_SCORE_SECTION_CONFIG["408"]
    pattern = _heading_block_pattern(config["heading"], 2)
    match = pattern.search(text)
    if not match:
        return text

    block = match.group(2)
    expected_cols = len(config["columns"])
    new_lines: List[str] = []
    changed = False

    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            new_lines.append(line)
            continue
        cells = [cell.strip() for cell in stripped.split("|")[1:-1]]

        # 头行
        if cells and cells[0] == "日期":
            if len(cells) != expected_cols:
                new_lines.append(f"| {' | '.join(config['headers'])} |")
                changed = True
            else:
                new_lines.append(line)
            continue

        # 分隔行
        if _is_separator_row(cells):
            if len(cells) != expected_cols:
                new_lines.append(config["separator"])
                changed = True
            else:
                new_lines.append(line)
            continue

        # 空白占位行
        if _is_blank_row(cells):
            if len(cells) != expected_cols:
                new_lines.append(config["blank"])
                changed = True
            else:
                new_lines.append(line)
            continue

        # 数据行 — 按列数迁移
        if len(cells) == 6:
            date_cell, paper_type, paper, total, issues, note = cells
            new_line = (
                f"| {date_cell} | {paper_type} | {paper} |  |  |  |  | "
                f"{total} | {issues} | {note} |"
            )
            new_lines.append(new_line)
            changed = True
            continue

        if len(cells) == 9:
            date_cell, paper, ds, co, os_cell, cn, total, issues, note = cells
            paper_type = "真题" if "真题" in paper else "模拟"
            new_line = (
                f"| {date_cell} | {paper_type} | {paper} | {ds} | {co} | {os_cell} | {cn} | "
                f"{total} | {issues} | {note} |"
            )
            new_lines.append(new_line)
            changed = True
            continue

        new_lines.append(line)

    if not changed:
        return text

    new_block = "\n".join(new_lines)
    return text[:match.start(2)] + new_block + ("\n" if not new_block.endswith("\n") else "") + text[match.end(2):]


def migrate_archive_schemas(text: str) -> str:
    """对档案应用所有已知的 schema 迁移。幂等:对已迁移文本是 no-op。"""
    return _migrate_408_table(text)

