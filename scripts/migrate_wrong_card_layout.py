#!/usr/bin/env python3
"""一次性重排已有错题卡里拥挤的详解小节。

用法:
  python3 scripts/migrate_wrong_card_layout.py [OBSIDIAN_ROOT] [--apply]

默认 dry-run（只报告，不写盘）；加 --apply 才落盘。

自动修复（安全、确定性）：
- `考点判断`/`考点定位` 里把 ≥2 个结构化字段挤进同一行的 bullet → 按字段标签边界拆成多行
  （在标签处切，不在句号处切，所以突破口里带 LaTeX 和句号的长值整段保留）
- `规范解法` 里被 render_bullet_block 加了 `- ` 的块公式（`- $$` 破损）→ 去掉前缀，
  让 `$$` 块公式独立成行，Obsidian 才能渲染

只报告不改（语义拆分不安全，分析明确警告别按句号机械拆）：
- 任意详解小节里散文 > MAX_DETAIL_LINE_LENGTH 字的 bullet → 列出路径+小节+摘要，供人工处理

安全边界：
- 永不触碰 YAML frontmatter / `### 题目` / `### 历史记录`
- 幂等：已经规范的卡再跑一次不产生改动
- 输出 JSON 报告 {applied, cards_scanned, changed, overlong_manual_review, skipped, summary}
"""
import argparse
import json
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from create_wrong_card import (
    MAX_DETAIL_LINE_LENGTH,
    STRUCTURED_POINT_LABELS,
    count_structured_labels,
    visual_len,
)
from env_util import atomic_write, is_icloud_placeholder, json_error, resolve_obsidian_root

# 把多字段挤一行拆开的小节
LABEL_SPLIT_SECTIONS = ("考点判断", "考点定位")
# 修复 `- $$` 块公式破损的小节
FORMULA_UNWRAP_SECTIONS = ("规范解法",)
# 只报告超长散文行的小节（数学一 + 408 详解小节）
OVERLONG_REPORT_SECTIONS = (
    "考点判断", "第一步怎么想到", "规范解法", "错因定位", "易错点", "下次怎么做",
    "考点定位", "题干突破口", "选项逐个辨析", "双轨解释", "干扰项陷阱",
    "知识网络串联", "记忆钩子",
)
# 块公式定界行：可能被错误加了 `- ` 前缀
DISPLAY_DELIM_RE = re.compile(r"^\s*(?:-\s+)?\$\$\s*$")


def section_block_re(heading: str) -> "re.Pattern[str]":
    """匹配 `### heading` 小节体（到下一个 `### ` 或文末）。group(2) 含尾随空白。"""
    return re.compile(
        rf"(^[ \t]{{0,3}}### {re.escape(heading)}\r?\n)(.*?)(?=^[ \t]{{0,3}}### |\Z)",
        re.M | re.S,
    )


def rewrite_section(
    text: str, heading: str, transform: Callable[[str], Optional[str]]
) -> Tuple[str, bool]:
    """对单个小节体应用 transform。保留原小节的尾随空白（含小节间的空行），
    保证只动内容、不改版式；transform 返回 None 表示无需改动。"""
    match = section_block_re(heading).search(text)
    if not match:
        return text, False
    original_body = match.group(2)
    content = original_body.rstrip("\n")
    trailing = original_body[len(content):]
    new_content = transform(content)
    if new_content is None or new_content == content:
        return text, False
    return text[: match.start(2)] + new_content + trailing + text[match.end(2):], True


def section_body(text: str, heading: str) -> Optional[str]:
    match = section_block_re(heading).search(text)
    return match.group(2).rstrip("\n") if match else None


def split_label_bullet(content: str) -> Optional[List[str]]:
    """把一条含 ≥2 个结构化字段的 bullet 内容按字段标签拆成多段。

    半角冒号先归一化定位，但切分用原文（保留原始写法）；每段去掉作为分隔符的尾随句号。
    """
    normalized = content.replace(":", "：")
    positions: List[int] = []
    for label in STRUCTURED_POINT_LABELS:
        token = f"{label}："
        start = 0
        while True:
            idx = normalized.find(token, start)
            if idx == -1:
                break
            positions.append(idx)
            start = idx + len(token)
    if len(positions) < 2:
        return None
    positions = sorted(set(positions))
    fields: List[str] = []
    for i, idx in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(content)
        segment = content[idx:end].strip().rstrip("。").strip()
        if segment:
            fields.append(segment)
    return fields if len(fields) >= 2 else None


def transform_label_section(block: str) -> Optional[str]:
    """把小节里每个含 ≥2 字段的 bullet 拆开。返回新 block，或 None（无变化）。"""
    out: List[str] = []
    changed = False
    for line in block.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- "):
            inner = stripped[2:].strip()
            if count_structured_labels(inner) >= 2:
                fields = split_label_bullet(inner)
                if fields:
                    out.extend(f"- {field}" for field in fields)
                    changed = True
                    continue
        out.append(line)
    return "\n".join(out) if changed else None


def unwrap_bulleted_block_math(block: str) -> Optional[str]:
    """去掉块公式定界行/块内行被错误添加的 `- ` 前缀。

    用状态机跟踪是否在 `$$...$$` 块内；块内的 `- xxx` 行去掉前缀，定界行统一写成裸 `$$`。
    若 `$$` 不成对（块未闭合）则保守放弃本小节修复，返回 None。
    """
    lines = block.split("\n")
    out: List[str] = []
    in_block = False
    changed = False
    for line in lines:
        if DISPLAY_DELIM_RE.match(line):
            if line.strip() != "$$":
                changed = True
            out.append("$$")
            in_block = not in_block
            continue
        if in_block:
            stripped = line.lstrip()
            if stripped.startswith("- "):
                out.append(stripped[2:])
                changed = True
                continue
        out.append(line)
    if in_block:  # 不成对，放弃修复以免损坏
        return None
    return "\n".join(out) if changed else None


def find_overlong_bullets(block: str) -> List[str]:
    flags: List[str] = []
    for line in block.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        inner = stripped[2:].strip()
        if visual_len(inner) > MAX_DETAIL_LINE_LENGTH:
            flags.append(inner[:50] + ("…" if len(inner) > 50 else ""))
    return flags


def migrate_card(text: str) -> Tuple[str, Dict]:
    """返回 (new_text, report)。report 含 label_splits / formula_unwraps / overlong_flags。"""
    report: Dict = {"label_splits": [], "formula_unwraps": [], "overlong_flags": []}
    new_text = text
    for heading in LABEL_SPLIT_SECTIONS:
        new_text, changed = rewrite_section(new_text, heading, transform_label_section)
        if changed:
            report["label_splits"].append(heading)
    for heading in FORMULA_UNWRAP_SECTIONS:
        new_text, changed = rewrite_section(new_text, heading, unwrap_bulleted_block_math)
        if changed:
            report["formula_unwraps"].append(heading)
    for heading in OVERLONG_REPORT_SECTIONS:
        body = section_body(new_text, heading)
        if body is None:
            continue
        for excerpt in find_overlong_bullets(body):
            report["overlong_flags"].append({"section": heading, "excerpt": excerpt})
    return new_text, report


def main() -> None:
    parser = argparse.ArgumentParser(description="重排错题卡拥挤详解小节")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    parser.add_argument("--apply", action="store_true", help="实际写盘；默认只预览(dry-run)")
    args = parser.parse_args()

    obsidian_root = resolve_obsidian_root(args.obsidian_root)
    if not obsidian_root.exists():
        json_error(f"obsidian_root 不存在: {obsidian_root}")

    cards_root = obsidian_root / "错题本"
    changed_files: List[Dict] = []
    overlong_files: List[Dict] = []
    skipped: List[Dict] = []
    scanned = 0

    if cards_root.exists():
        for card in sorted(cards_root.rglob("*.md")):
            rel = str(card.relative_to(obsidian_root))
            if is_icloud_placeholder(card):
                skipped.append({"path": rel, "reason": "iCloud 占位符未下载"})
                continue
            scanned += 1
            text = card.read_text(encoding="utf-8")
            new_text, report = migrate_card(text)
            if new_text != text:
                if args.apply:
                    atomic_write(card, new_text)
                changed_files.append({
                    "path": rel,
                    "label_splits": report["label_splits"],
                    "formula_unwraps": report["formula_unwraps"],
                })
            if report["overlong_flags"]:
                overlong_files.append({"path": rel, "flags": report["overlong_flags"]})

    print(json.dumps({
        "applied": args.apply,
        "cards_scanned": scanned,
        "changed": changed_files,
        "overlong_manual_review": overlong_files,
        "skipped": skipped,
        "summary": {
            "changed_count": len(changed_files),
            "overlong_count": sum(len(f["flags"]) for f in overlong_files),
            "skipped_count": len(skipped),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
