#!/usr/bin/env python3
"""初始化考研 Obsidian vault 的目录和基础模板。

用法:
  python3 init_vault.py [OBSIDIAN_ROOT]
  python3 init_vault.py --force
  环境变量 KAOYAN_OBSIDIAN_ROOT 可替代 CLI 参数

默认只创建缺失的目录/文件，不覆盖已有内容；加 --force 时会重写模板文件。
"""
import argparse
import json
import sys
from pathlib import Path

from env_util import resolve_obsidian_root, resolve_skill_root, atomic_write


SUBJECT_FILES = ["数学一.md", "408.md", "政治.md", "英语一.md"]
ROOT_DIRS = [
    "知识地图", "学习日志",
    "错题本", "错题本/数学一", "错题本/408", "错题本/政治", "错题本/英语一",
    "知识笔记", "知识笔记/408", "复盘报告", "周计划",
]


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


def main():
    parser = argparse.ArgumentParser(description="初始化考研 Obsidian vault")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录（可由环境变量替代）")
    parser.add_argument("--force", action="store_true", help="覆盖已有模板文件")
    args = parser.parse_args()

    root = resolve_obsidian_root(args.obsidian_root)
    template_text = load_template_text()

    created_dirs = []
    created_files = []
    overwritten_files = []
    skipped_files = []

    root.mkdir(parents=True, exist_ok=True)
    for rel_dir in ROOT_DIRS:
        directory = root / rel_dir
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(directory))

    archive_content = extract_markdown_block(template_text, "## Part 1: 摘要档案")
    archive_path = root / "我的学习者档案.md"
    write_template_file(archive_path, archive_content, args.force, created_files, overwritten_files, skipped_files)

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
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
