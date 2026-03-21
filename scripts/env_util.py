"""共享工具函数：环境变量解析、原子写入、安全类型转换、iCloud 检测。"""
import os
import sys
from pathlib import Path


def resolve_obsidian_root(cli_arg=None):
    """解析 Obsidian vault 根目录。优先级：CLI 参数 > 环境变量 > 报错退出。"""
    if cli_arg:
        return Path(cli_arg)
    env = os.environ.get("KAOYAN_OBSIDIAN_ROOT")
    if env:
        return Path(env)
    print('{"error": true, "message": "需要指定 OBSIDIAN_ROOT：传入 CLI 参数或设置 KAOYAN_OBSIDIAN_ROOT 环境变量"}')
    sys.exit(1)


def resolve_skill_root(cli_arg=None):
    """解析 skill 根目录。优先级：CLI 参数 > 环境变量 > 从 __file__ 推算。"""
    if cli_arg:
        return Path(cli_arg)
    env = os.environ.get("KAOYAN_SKILL_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def atomic_write(path, content, encoding="utf-8"):
    """原子写入：先写 .tmp 再 rename，防止崩溃时损坏原文件。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding=encoding)
    tmp.rename(path)


def safe_int(val, default=1):
    """安全 int 转换，失败时返回默认值。"""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def safe_float(val, default=2.5):
    """安全 float 转换，失败时返回默认值。"""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def is_icloud_placeholder(path):
    """检测文件是否为 iCloud 占位符（未下载到本地）。

    macOS iCloud 占位符的命名规则：foo.md → .foo.md.icloud
    """
    placeholder = path.parent / f".{path.name}.icloud"
    return placeholder.exists()


def json_error(message):
    """输出 JSON 格式的错误信息到 stdout 并退出。"""
    import json
    print(json.dumps({"error": True, "message": message}, ensure_ascii=False))
    sys.exit(1)
