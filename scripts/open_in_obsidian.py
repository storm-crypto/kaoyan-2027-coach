#!/usr/bin/env python3
"""把 vault 内的文件用 `obsidian://open` URI 在 Obsidian 里打开（JSON 输出）。

用法: python3 open_in_obsidian.py [OBSIDIAN_ROOT] (--path 文件路径 | --question-id qid-xxxx)
                                  [--background] [--print-only]
      环境变量 KAOYAN_OBSIDIAN_ROOT 可替代 CLI 参数

存在的理由：CLI/对话框里的题面是 `latex_to_unicode` 降级出来的近似文本，而错题卡本体
在 Obsidian 里有完整渲染的 LaTeX 和排好版的详解。`/review` 出题、`/wrong` 建卡、
`/plan_today` 生成计划后调这个脚本，用户就能直接读原文，不用自己去库里翻。

vault 根不等于 OBSIDIAN_ROOT：错题本在 `<vault>/10_Projects/Kaoyan_2027_Prep/` 这类
子目录下也很常见，所以 vault 根统一从目标文件向上找 `.obsidian/` 目录来判定，
找不到才退回 OBSIDIAN_ROOT。
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from env_util import is_icloud_placeholder, json_error, resolve_obsidian_root
from study_ops import iter_review_cards

# Obsidian 的库注册表，用来确认目标库确实被 Obsidian 认识（否则 URI 会静默打不开）
OBSIDIAN_REGISTRY = Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"


def find_vault_root(start: Path, fallback: Path) -> Tuple[Path, bool]:
    """从 start 逐级向上找含 `.obsidian/` 的目录。返回 (vault 根, 是否真的找到)。"""
    for candidate in [start, *start.parents]:
        if (candidate / ".obsidian").is_dir():
            return candidate, True
    return fallback, False


def lookup_registered_vault(vault_root: Path) -> Optional[str]:
    """在 Obsidian 注册表里按路径反查库名；查不到返回 None。"""
    try:
        registry = json.loads(OBSIDIAN_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for entry in (registry.get("vaults") or {}).values():
        raw = entry.get("path")
        if not raw:
            continue
        try:
            if Path(raw).resolve() == vault_root:
                return Path(raw).name
        except OSError:
            continue
    return None


def build_uris(file_path: Path, vault_root: Path, vault_name: str) -> Dict[str, str]:
    """构造两种 open URI。

    `uri` 走 vault+file，是 Obsidian 最稳的形态；`uri_by_path` 走绝对路径，
    留给库名对不上时手工兜底。file 参数按链接目标解析，所以 `.md` 要去掉。
    """
    rel = file_path.relative_to(vault_root)
    target = rel.with_suffix("") if rel.suffix == ".md" else rel
    return {
        "uri": f"obsidian://open?vault={quote(vault_name, safe='')}&file={quote(target.as_posix(), safe='')}",
        "uri_by_path": f"obsidian://open?path={quote(str(file_path), safe='')}",
    }


def find_card_by_question_id(obsidian_root: Path, question_id: str) -> Optional[Path]:
    """跨科全库按 question_id 精确查卡，和 find_card.py 的主键语义保持一致。"""
    for item in iter_review_cards(obsidian_root):
        if (item["frontmatter"] or {}).get("question_id") == question_id:
            return item["path"]
    return None


def resolve_target(args: argparse.Namespace, obsidian_root: Path) -> Path:
    if args.question_id:
        found = find_card_by_question_id(obsidian_root, args.question_id)
        if found is None:
            json_error(f"错题本里没有 question_id 为 {args.question_id} 的卡片")
        return found.resolve()

    target = Path(args.path).expanduser()
    if not target.is_absolute():
        target = obsidian_root / target
    return target.resolve()


def open_uri(uri: str, background: bool) -> Tuple[bool, Optional[str]]:
    """调用 macOS `open` 唤起 Obsidian。返回 (是否成功, 失败原因)。"""
    if sys.platform != "darwin":
        return False, "非 macOS 环境，未执行 open；请手动点开返回的 uri"
    cmd = ["open", "-g", uri] if background else ["open", uri]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        return False, f"调用 open 失败：{exc}"
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"退出码 {proc.returncode}"
        return False, f"open 命令失败：{detail}"
    return True, None


def main() -> None:
    parser = argparse.ArgumentParser(description="在 Obsidian 里打开 vault 内的文件")
    parser.add_argument("obsidian_root", nargs="?", default=None, help="Obsidian vault 根目录")
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--path", help="要打开的文件路径（绝对路径，或相对 OBSIDIAN_ROOT）")
    target_group.add_argument("--question-id", dest="question_id", help="按错题卡 question_id 查找并打开")
    parser.add_argument("--background", action="store_true",
                        help="不把 Obsidian 切到前台（open -g），适合批量预热")
    parser.add_argument("--print-only", dest="print_only", action="store_true",
                        help="只返回 URI，不真的打开")
    args = parser.parse_args()

    obsidian_root = resolve_obsidian_root(args.obsidian_root).resolve()
    target = resolve_target(args, obsidian_root)
    if not target.exists():
        json_error(f"文件不存在：{target}")

    vault_root, detected = find_vault_root(target.parent, obsidian_root)
    try:
        target.relative_to(vault_root)
    except ValueError:
        json_error(f"文件不在 vault 内，无法生成 obsidian URI：{target} 不在 {vault_root} 下")

    registered_name = lookup_registered_vault(vault_root)
    vault_name = registered_name or vault_root.name

    warnings: List[str] = []
    if not detected:
        warnings.append(f"没找到 .obsidian/ 目录，已退回 OBSIDIAN_ROOT 当 vault 根：{vault_root}")
    if registered_name is None:
        warnings.append(f"Obsidian 注册表里没有这个库，URI 可能打不开；已按目录名当库名：{vault_name}")
    if is_icloud_placeholder(target):
        warnings.append("该文件还是 iCloud 占位符，打开时会先触发下载，可能略慢")

    result = {
        "path": str(target),
        "vault": vault_name,
        "vault_root": str(vault_root),
        "opened": False,
        **build_uris(target, vault_root, vault_name),
    }

    if not args.print_only:
        opened, failure = open_uri(result["uri"], args.background)
        result["opened"] = opened
        if failure:
            warnings.append(failure)

    if warnings:
        result["warnings"] = warnings
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
