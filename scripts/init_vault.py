#!/usr/bin/env python3
"""初始化考研 Obsidian vault 的目录和基础模板。

用法:
  python3 init_vault.py [OBSIDIAN_ROOT]
  python3 init_vault.py --force
  python3 init_vault.py [OBSIDIAN_ROOT] --school-major 计算机科学与技术 --target-total 360 --exam-date 2026-12-20 --daily-hours 6 --stage "数学提速期"
  环境变量 KAOYAN_OBSIDIAN_ROOT 可替代 CLI 参数

默认只创建缺失的目录/文件，不覆盖已有内容；加 --force 时会重写模板文件。
传入基础信息参数时，会把这些值回填到 `我的学习者档案.md` 的“基本信息”区域；
若档案已存在且未加 --force，则只补空字段，不覆盖已有内容。
"""
import argparse
import json
import sys
import re
from datetime import date
from pathlib import Path

from env_util import resolve_obsidian_root, resolve_skill_root, atomic_write


SUBJECT_FILES = ["数学一.md", "408.md", "政治.md", "英语一.md"]
ROOT_DIRS = [
    "知识地图", "学习日志",
    "错题本", "错题本/数学一", "错题本/408", "错题本/政治", "错题本/英语一",
    "知识笔记", "知识笔记/408", "复盘报告", "周计划",
]

ARCHIVE_FIELD_LABELS = {
    "school_major": "目标院校/专业",
    "target_total": "当前目标总分",
    "exam_date": "考试日期",
    "daily_hours": "每日可投入时长",
    "updated_at": "最近更新日期",
    "stage": "当前阶段关键词",
}

DEFAULT_FIELD_VALUES = {
    "考试日期": {"（以当年公告为准）"},
    "最近更新日期": {"YYYY-MM-DD"},
    "当前阶段关键词": {"如「408重构期 / 数学提速期 / 冲刺期」"},
}


def load_template_text():
    skill_root = resolve_skill_root()
    template_path = skill_root / "templates" / "学习者档案与知识地图模板.md"
    if not template_path.exists():
        print(json.dumps({"error": True, "message": f"模板不存在: {template_path}"}, ensure_ascii=False))
        sys.exit(1)
    return template_path.read_text(encoding="utf-8")


def extract_markdown_block(text, anchor):
    anchor_index = text.find(anchor)
    if anchor_index == -1:
        raise ValueError(f"未找到锚点: {anchor}")
    block_start = text.find("```markdown", anchor_index)
    if block_start == -1:
        raise ValueError(f"锚点后未找到 markdown 代码块: {anchor}")
    content_start = block_start + len("```markdown\n")
    content_end = text.find("```", content_start)
    if content_end == -1:
        raise ValueError(f"markdown 代码块未闭合: {anchor}")
    return text[content_start:content_end].strip() + "\n"


def write_template_file(path, content, force, created_files, overwritten_files, skipped_files):
    existed_before = path.exists()
    if existed_before and not force:
        skipped_files.append(str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, content)
    if existed_before:
        overwritten_files.append(str(path))
    else:
        created_files.append(str(path))


def collect_profile_updates(args):
    profile = {
        "school_major": args.school_major or "",
        "target_total": str(args.target_total) if args.target_total is not None else "",
        "exam_date": args.exam_date or "",
        "daily_hours": str(args.daily_hours) if args.daily_hours is not None else "",
        "updated_at": args.updated_at or "",
        "stage": args.stage or "",
    }
    has_user_input = any(
        value for key, value in profile.items()
        if key != "updated_at"
    )
    if has_user_input and not profile["updated_at"]:
        profile["updated_at"] = date.today().isoformat()
    return profile


def apply_archive_profile(content, profile, overwrite=False):
    updated_fields = []
    updated_content = content

    for key, label in ARCHIVE_FIELD_LABELS.items():
        value = profile.get(key, "")
        if not value:
            continue

        pattern = rf"(- \*\*{re.escape(label)}\*\*：)(.*)"
        match = re.search(pattern, updated_content)
        if not match:
            continue

        current_value = match.group(2).strip()
        placeholder_values = DEFAULT_FIELD_VALUES.get(label, set())
        should_write = overwrite or not current_value or current_value in placeholder_values
        if not should_write or current_value == value:
            continue

        updated_content = re.sub(pattern, lambda m: f"{m.group(1)}{value}", updated_content, count=1)
        updated_fields.append(label)

    return updated_content, updated_fields


def main():
    parser = argparse.ArgumentParser(description="初始化考研 Obsidian vault")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录（可由环境变量替代）")
    parser.add_argument("--force", action="store_true", help="覆盖已有模板文件")
    parser.add_argument("--school-major", help="目标院校/专业")
    parser.add_argument("--target-total", help="当前目标总分")
    parser.add_argument("--exam-date", help="考试日期 YYYY-MM-DD")
    parser.add_argument("--daily-hours", help="每日可投入时长")
    parser.add_argument("--stage", help="当前阶段关键词")
    parser.add_argument("--updated-at", help="最近更新日期 YYYY-MM-DD")
    args = parser.parse_args()

    root = resolve_obsidian_root(args.obsidian_root)
    template_text = load_template_text()
    profile = collect_profile_updates(args)

    created_dirs = []
    created_files = []
    overwritten_files = []
    skipped_files = []
    profile_updated_fields = []

    root.mkdir(parents=True, exist_ok=True)
    for rel_dir in ROOT_DIRS:
        directory = root / rel_dir
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(directory))

    archive_content = extract_markdown_block(template_text, "## Part 1: 摘要档案")
    archive_path = root / "我的学习者档案.md"
    write_template_file(archive_path, archive_content, args.force, created_files, overwritten_files, skipped_files)
    archive_text = archive_path.read_text(encoding="utf-8")
    updated_archive_text, profile_updated_fields = apply_archive_profile(archive_text, profile, overwrite=args.force)
    if updated_archive_text != archive_text:
        atomic_write(archive_path, updated_archive_text)
        archive_path_str = str(archive_path)
        if archive_path_str in skipped_files:
            skipped_files.remove(archive_path_str)
            overwritten_files.append(archive_path_str)

    for filename in SUBJECT_FILES:
        content = extract_markdown_block(template_text, f"### `知识地图/{filename}`")
        file_path = root / "知识地图" / filename
        write_template_file(file_path, content, args.force, created_files, overwritten_files, skipped_files)

    print(json.dumps({
        "root": str(root),
        "created_dirs": created_dirs,
        "created_files": created_files,
        "overwritten_files": overwritten_files,
        "skipped_files": skipped_files,
        "profile_updated_fields": profile_updated_fields,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
