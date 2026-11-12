#!/bin/bash
# 检查依赖并创建 Claude Code / Codex 入口；--check 全程只读。

set -e

usage() {
    echo "用法: bash setup.sh [--check]"
    echo "  --check 只检查 Python、依赖、链接和学习库路径，不创建或修改文件。"
}

CHECK_ONLY=0
if [ "$#" -gt 1 ]; then
    usage >&2
    exit 2
fi
case "${1:-}" in
    --check) CHECK_ONLY=1 ;;
    --help|-h) usage; exit 0 ;;
    "") ;;
    *) usage >&2; exit 2 ;;
esac

SKILL_DIR="$(cd "$(dirname "$0")" && pwd -P)"

echo "=== 考研2027教练 Skill 设置 ==="
echo "Skill 目录: $SKILL_DIR"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] 未找到 python3，请先安装 Python 3.9+"
    exit 1
fi
if ! PY_VERSION=$(python3 -B -c 'import sys; print(sys.version.split()[0]); sys.exit(0 if sys.version_info >= (3, 9) else 1)'); then
    echo "[ERROR] 需要 Python 3.9+，当前 python3 为 ${PY_VERSION:-无法运行}"
    exit 1
fi
echo "[OK] Python $PY_VERSION"

ISSUES=0
MISSING_LINKS=()
check_symlink() {
    local target_dir="$1"
    local tool_name="$2"
    local link_path="$target_dir/kaoyan-2027-coach"

    if [ -L "$link_path" ]; then
        if [ ! -e "$link_path" ]; then
            echo "[ERROR] $tool_name 链接已失效: $link_path -> $(readlink "$link_path")"
            ISSUES=1
        elif python3 -B -c 'from pathlib import Path; import sys; sys.exit(0 if Path(sys.argv[1]).resolve() == Path(sys.argv[2]).resolve() else 1)' "$link_path" "$SKILL_DIR"; then
            echo "[OK] $tool_name 链接指向当前 skill"
        else
            echo "[ERROR] $tool_name 链接指向其他位置: $link_path -> $(readlink "$link_path")"
            echo "        当前 skill: $SKILL_DIR"
            ISSUES=1
        fi
    elif [ -e "$link_path" ]; then
        echo "[ERROR] $link_path 已是实际文件或目录，保留原内容；请先核对安装位置。"
        ISSUES=1
    elif [ "$CHECK_ONLY" -eq 1 ]; then
        echo "[MISSING] $tool_name 入口尚未创建: $link_path"
        ISSUES=1
    else
        MISSING_LINKS+=("$link_path")
    fi
}

check_symlink "$HOME/.claude/skills" "Claude Code"
check_symlink "$HOME/.codex/skills" "Codex"

has_figure_packages() {
    "$1" -B -c 'import importlib.util; import sys; sys.exit(0 if all(importlib.util.find_spec(name) is not None for name in ("matplotlib", "numpy")) else 1)' >/dev/null 2>&1
}
if has_figure_packages python3; then
    echo "[OK] 当前 Python 可用绘图库 matplotlib / numpy"
elif [ -x "$SKILL_DIR/.venv/bin/python" ] && has_figure_packages "$SKILL_DIR/.venv/bin/python"; then
    echo "[OK] skill .venv 可用绘图库 matplotlib / numpy"
else
    echo "[OPTIONAL] 尚未找到 matplotlib / numpy；普通记录可用，Python 配图前需安装到当前解释器或 skill .venv。"
fi

echo ""

# 环境变量提示
if [ -z "${KAOYAN_OBSIDIAN_ROOT:-}" ]; then
    echo "[MISSING] 尚未配置 KAOYAN_OBSIDIAN_ROOT。"
    if [ "$CHECK_ONLY" -eq 1 ]; then ISSUES=1; fi
    echo "=== 环境变量设置 ==="
    echo ""
    echo "请将以下内容添加到你的 shell 配置文件（~/.zshrc 或 ~/.bashrc）："
    echo ""
    echo '  export KAOYAN_OBSIDIAN_ROOT="/path/to/your/obsidian/vault/Kaoyan_2027_Prep"'
    echo ""
    echo "然后运行: source ~/.zshrc"
elif [ -e "$KAOYAN_OBSIDIAN_ROOT" ] && [ ! -d "$KAOYAN_OBSIDIAN_ROOT" ]; then
    echo "[ERROR] KAOYAN_OBSIDIAN_ROOT 不是目录: $KAOYAN_OBSIDIAN_ROOT"
    ISSUES=1
elif [ ! -d "$KAOYAN_OBSIDIAN_ROOT" ]; then
    echo "[MISSING] 学习库尚未创建: ${KAOYAN_OBSIDIAN_ROOT}；确认路径后用 /load 初始化。"
    if [ "$CHECK_ONLY" -eq 1 ]; then ISSUES=1; fi
elif [ ! -r "$KAOYAN_OBSIDIAN_ROOT" ] || [ ! -w "$KAOYAN_OBSIDIAN_ROOT" ]; then
    echo "[ERROR] 学习库目录不可读写: $KAOYAN_OBSIDIAN_ROOT"
    ISSUES=1
else
    echo "[OK] 学习库路径可用: $KAOYAN_OBSIDIAN_ROOT"
fi

echo ""
if [ "$ISSUES" -ne 0 ]; then
    echo "检查未通过；没有创建或替换任何入口。修复上述位置后重新运行。"
    exit 1
fi
if [ "$CHECK_ONLY" -eq 1 ]; then
    echo "检查通过；没有修改链接或配置。"
else
    # 所有既有入口检查通过后才创建缺失项；不用 -f，避免覆盖并发创建的文件。
    for link_path in "${MISSING_LINKS[@]}"; do
        mkdir -p "$(dirname "$link_path")"
        ln -s "$SKILL_DIR" "$link_path"
        echo "[OK] 已创建入口: $link_path -> $SKILL_DIR"
    done
    echo "安装入口已就绪；配置好 KAOYAN_OBSIDIAN_ROOT 后，用 /load 开始。"
fi
