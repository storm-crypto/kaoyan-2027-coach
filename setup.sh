#!/bin/bash
# 考研2027教练 Skill 跨平台设置脚本
# 创建 symlink 让 Claude Code、Codex 等工具也能使用此 skill

set -e

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== 考研2027教练 Skill 设置 ==="
echo "Skill 目录: $SKILL_DIR"
echo ""

# 检查 Python 版本
if command -v python3 &> /dev/null; then
    PY_VERSION=$(python3 --version 2>&1)
    echo "[OK] $PY_VERSION"
else
    echo "[ERROR] 未找到 python3，请先安装 Python 3.6+"
    exit 1
fi

# 创建 symlink
create_symlink() {
    local target_dir="$1"
    local tool_name="$2"
    local link_path="$target_dir/kaoyan-2027-coach"

    if [ -L "$link_path" ]; then
        echo "[OK] $tool_name symlink 已存在"
    elif [ -d "$link_path" ]; then
        echo "[SKIP] $link_path 是真实目录，跳过（避免覆盖）"
    else
        mkdir -p "$target_dir"
        ln -sf "$SKILL_DIR" "$link_path"
        echo "[OK] 已创建 $tool_name symlink: $link_path -> $SKILL_DIR"
    fi
}

create_symlink "$HOME/.claude/skills" "Claude Code"
create_symlink "$HOME/.codex/skills" "Codex"
# Gemini/Antigravity: skill 已在原位，无需 symlink

echo ""

# 环境变量提示
if [ -z "$KAOYAN_OBSIDIAN_ROOT" ]; then
    echo "=== 环境变量设置 ==="
    echo ""
    echo "请将以下内容添加到你的 shell 配置文件（~/.zshrc 或 ~/.bashrc）："
    echo ""
    echo '  export KAOYAN_OBSIDIAN_ROOT="/path/to/your/obsidian/vault/Kaoyan_2027_Prep"'
    echo ""
    echo "然后运行: source ~/.zshrc"
else
    echo "[OK] KAOYAN_OBSIDIAN_ROOT 已设置: $KAOYAN_OBSIDIAN_ROOT"
fi

echo ""
echo "设置完成！现在可以在 Claude Code、Codex、Gemini CLI 中使用此 skill。"
