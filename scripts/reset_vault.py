#!/usr/bin/env python3
"""重置考研 Obsidian vault 到干净起点。

默认是“软重置”：
- 清空学习日志、周计划、复盘报告、错题本
- 重置学习者档案和知识地图
- 保留基础建档信息（院校/总分/考试日期/每日时长/阶段）
- 默认不动知识笔记，避免误删手写内容

加 --hard 时，基础建档信息也一并清空，回到首次初始化模板。
加 --include-notes 时，同时清空知识笔记目录。

本脚本是破坏性操作，必须显式传入 --yes。
"""
import argparse
import json
import re
import shutil
from pathlib import Path

from env_util import atomic_write, json_error, resolve_obsidian_root
from init_vault import (
    ARCHIVE_FIELD_LABELS,
    DEFAULT_FIELD_VALUES,
    ROOT_DIRS,
    SUBJECT_FILES,
    apply_archive_profile,
    extract_markdown_block,
    load_template_text,
)
from study_ops import parse_today


PRESERVED_PROFILE_KEYS = ("school_major", "target_total", "exam_date", "daily_hours", "stage")


def parse_args():
    parser = argparse.ArgumentParser(description="重置考研 Obsidian vault")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录（可由环境变量替代）")
    parser.add_argument("--hard", action="store_true", help="彻底清空基础建档信息，回到空白模板")
    parser.add_argument("--include-notes", action="store_true", help="同时清空知识笔记目录")
    parser.add_argument("--yes", action="store_true", help="确认执行破坏性重置")
    parser.add_argument("--today", help="用于测试的日期 YYYY-MM-DD")
    return parser.parse_args()
def count_tree(path):
    if not path.exists():
        return {"path": str(path), "files_removed": 0, "dirs_removed": 0}
    file_count = 0
    dir_count = 0
    for item in path.rglob("*"):
        if item.is_dir():
            dir_count += 1
        else:
            file_count += 1
    return {"path": str(path), "files_removed": file_count, "dirs_removed": dir_count}


def clear_directory(path):
    stats = count_tree(path)
    if path.exists():
        shutil.rmtree(path)
    return stats


def extract_archive_field(text, label):
    match = re.search(rf"^- \*\*{re.escape(label)}\*\*[:：](.*)$", text, re.M)
    if not match:
        return ""
    value = match.group(1).strip()
    if value in DEFAULT_FIELD_VALUES.get(label, set()):
        return ""
    return value


def build_preserved_profile(archive_text, today):
    profile = {key: "" for key in ARCHIVE_FIELD_LABELS}
    for key in PRESERVED_PROFILE_KEYS:
        label = ARCHIVE_FIELD_LABELS[key]
        profile[key] = extract_archive_field(archive_text, label)
    if any(profile[key] for key in PRESERVED_PROFILE_KEYS):
        profile["updated_at"] = today.isoformat()
    return profile


def recreate_managed_dirs(root):
    recreated = []
    root.mkdir(parents=True, exist_ok=True)
    for rel_dir in ROOT_DIRS:
        directory = root / rel_dir
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            recreated.append(str(directory))
    knowledge_dir = root / "知识地图"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    if str(knowledge_dir) not in recreated:
        recreated.append(str(knowledge_dir))
    return recreated


def reset_archive(root, template_text, profile):
    archive_content = extract_markdown_block(template_text, "## Part 1: 摘要档案")
    updated_content, updated_fields = apply_archive_profile(archive_content, profile, overwrite=True)
    archive_path = root / "我的学习者档案.md"
    atomic_write(archive_path, updated_content)
    return str(archive_path), updated_fields


def reset_knowledge_maps(root, template_text):
    written_files = []
    knowledge_dir = root / "知识地图"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    for filename in SUBJECT_FILES:
        content = extract_markdown_block(template_text, f"### `知识地图/{filename}`")
        file_path = knowledge_dir / filename
        atomic_write(file_path, content)
        written_files.append(str(file_path))
    return written_files


def main():
    args = parse_args()
    if not args.yes:
        json_error("reset 是破坏性操作，请显式传入 --yes 确认后再执行")

    root = resolve_obsidian_root(args.obsidian_root)
    if not root.exists():
        json_error(f"vault 不存在: {root}")

    today = parse_today(args.today)
    template_text = load_template_text()

    archive_path = root / "我的学习者档案.md"
    archive_text = archive_path.read_text(encoding="utf-8") if archive_path.exists() else ""
    profile = {} if args.hard else build_preserved_profile(archive_text, today)

    managed_dirs = [
        root / "学习日志",
        root / "周计划",
        root / "复盘报告",
        root / "错题本",
    ]
    if args.include_notes:
        managed_dirs.append(root / "知识笔记")

    cleared_targets = [clear_directory(path) for path in managed_dirs]
    recreated_dirs = recreate_managed_dirs(root)
    archive_file, preserved_fields = reset_archive(root, template_text, profile)
    knowledge_map_files = reset_knowledge_maps(root, template_text)

    print(json.dumps({
        "root": str(root),
        "mode": "hard" if args.hard else "soft",
        "notes_cleared": args.include_notes,
        "cleared_targets": cleared_targets,
        "recreated_dirs": recreated_dirs,
        "reset_files": [archive_file] + knowledge_map_files,
        "preserved_profile_fields": preserved_fields,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
