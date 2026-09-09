"""错题卡配图（SVG / TikZ / Mermaid）的共享解析与渲染逻辑。

建卡（create_wrong_card.py）和复习补图（update_card.py）都要把 `create_figure.py` 产出的
`figure_arg`（`"vault相对路径|图N：说明[|宽度]"`）落成卡片里的「嵌入 + 说明」块，
两边必须用同一套解析、同一套排版、同一套插入位置规则，所以统一收口在这里。

三种图源的落法不同，但对调用方是同一个 `figure_arg`：
- `.svg`  → `![[路径|宽度]]`，Obsidian 以 <img> 渲染
- `.tikz` → 把源码内联成 ```tikz 代码块，由 TikZJax 插件在打开卡片时编译
- `.mmd`  → 把源码内联成 ```mermaid 代码块，Obsidian 原生渲染
代码块前留一行 `%%图源：路径%%` Obsidian 注释（阅读视图不可见），重画时能追溯到源文件。
"""
import re
from pathlib import Path
from typing import List, Sequence, Tuple

from env_util import json_error

FIGURE_SPEC_SEPARATOR = "|"
DEFAULT_FIGURE_WIDTH = 480
MIN_FIGURE_WIDTH = 200
MAX_FIGURE_WIDTH = 900

# 图源后缀 → 卡片里的代码块语言。svg 不在这里：它走 ![[...]] 嵌入而不是代码块。
CODE_FIGURE_LANGS = {".tikz": "tikz", ".mmd": "mermaid"}
SUPPORTED_FIGURE_SUFFIXES = (".svg",) + tuple(CODE_FIGURE_LANGS)
FIGURE_SOURCE_COMMENT_PREFIX = "%%图源："

FIGURE_HEADING = "图示"
FIGURE_HEADING_LINE = f"### {FIGURE_HEADING}"

# 追加到已有图示区块时自己做定位：archive_ops.replace_heading_block 会把区块末尾的空行
# 规整掉，导致下一个 `### ` 标题贴在图说明后面，卡片读起来就挤成一坨。
FIGURE_SECTION_RE = re.compile(
    rf"(^[ \t]{{0,3}}### {FIGURE_HEADING}\r?\n)(.*?)(?=^[ \t]{{0,3}}### |\Z)",
    re.M | re.S,
)

# 图示区块统一插在「突破口类小节之后」，等价于「下面这个锚点小节之前」。
# 数学一：第一步怎么想到 → 图示 → 规范解法；408：题干突破口 → 图示 → 选项逐个辨析。
FIGURE_ANCHOR_HEADINGS = (
    "### 规范解法",
    "### 选项逐个辨析",
    "### 易错点 / 变式提醒",
    "### 历史记录",
)

# CLI/对话框里 `![[xxx.svg|480]]` 和 ```tikz / ```mermaid 代码块都是纯噪音
# （只有 Obsidian 渲染得出来），统一换成一句提示。
FIGURE_EMBED_LINE_RE = re.compile(r"^[ \t]*!\[\[[^\]\n]*?\.svg(?:\|[^\]\n]*)?\]\][ \t]*$", re.M | re.I)
FIGURE_CODE_BLOCK_RE = re.compile(
    r"^[ \t]*```(?:tikz|mermaid)[ \t]*\r?\n.*?^[ \t]*```[ \t]*$",
    re.M | re.S | re.I,
)
FIGURE_SOURCE_COMMENT_RE = re.compile(
    rf"^[ \t]*{re.escape(FIGURE_SOURCE_COMMENT_PREFIX)}[^\n]*%%[ \t]*\r?\n?", re.M
)
CLI_FIGURE_PLACEHOLDER = "（本题有配图，请在 Obsidian 中查看）"

# (vault 相对路径, 说明, 嵌入宽度, 源码)。源码只对 .tikz/.mmd 非空，svg 走文件嵌入不需要读内容。
FigureSpec = Tuple[str, str, int, str]


def parse_figure_specs(
    field_name: str,
    values: Sequence[str],
    obsidian_root: Path,
) -> List[FigureSpec]:
    """把 "vault相对路径|说明[|宽度]" 解析成 (相对路径, 说明, 宽度)。

    路径必须真实存在于 vault 内：卡片里一个指不到文件的 `![[...]]` 在 Obsidian 里
    是一条静默的死链接，等到复习时才发现就晚了，所以在落盘前 fail fast。
    """
    specs: List[FigureSpec] = []
    root = Path(obsidian_root).resolve()
    for raw in values:
        if not raw or not raw.strip():
            continue
        parts = [part.strip() for part in raw.split(FIGURE_SPEC_SEPARATOR)]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            json_error(
                f'{field_name} 格式应为 "vault相对路径|图N：说明[|宽度]"，实际收到: {raw}'
            )
        relative_raw, caption = parts[0], parts[1]
        width = DEFAULT_FIGURE_WIDTH
        if len(parts) >= 3 and parts[2]:
            try:
                width = int(parts[2])
            except ValueError:
                json_error(f"{field_name} 的宽度必须是整数，实际收到: {parts[2]}")
            if not MIN_FIGURE_WIDTH <= width <= MAX_FIGURE_WIDTH:
                json_error(
                    f"{field_name} 的宽度需在 {MIN_FIGURE_WIDTH}~{MAX_FIGURE_WIDTH} 之间，实际 {width}"
                )

        candidate = Path(relative_raw).expanduser()
        resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        try:
            relative_path = resolved.relative_to(root)
        except ValueError:
            json_error(f"{field_name} 指向 vault 之外的路径: {relative_raw}")
        suffix = resolved.suffix.lower()
        if suffix not in SUPPORTED_FIGURE_SUFFIXES:
            json_error(
                f"{field_name} 只接受 {' / '.join(SUPPORTED_FIGURE_SUFFIXES)} 图源，实际: {relative_raw}"
            )
        if not resolved.is_file():
            json_error(
                f"{field_name} 指向的配图不存在: {relative_raw}。"
                "请先用 create_figure.py 生成，再把它返回的 figure_arg 原样传进来"
            )
        source = ""
        if suffix in CODE_FIGURE_LANGS:
            source = resolved.read_text(encoding="utf-8").strip("\r\n")
            if not source.strip():
                json_error(f"{field_name} 指向的图源是空文件: {relative_raw}")
        specs.append((relative_path.as_posix(), caption, width, source))
    return specs


def figure_lang(path: str) -> str:
    """图源路径 → 代码块语言；svg 返回空串。"""
    return CODE_FIGURE_LANGS.get(Path(path).suffix.lower(), "")


def render_figure_embed(path: str, width: int, source: str) -> str:
    lang = figure_lang(path)
    if not lang:
        return f"![[{path}|{width}]]"
    return f"{FIGURE_SOURCE_COMMENT_PREFIX}{path}%%\n```{lang}\n{source}\n```"


def render_figure_block(specs: Sequence[FigureSpec]) -> str:
    """渲染成「嵌入 + 说明」成对的块，块之间空一行，Obsidian 里不会挤成一坨。"""
    chunks = [
        f"{render_figure_embed(path, width, source)}\n- {caption}"
        for path, caption, width, source in specs
    ]
    return "\n\n".join(chunks)


def figure_captions(specs: Sequence[FigureSpec]) -> List[str]:
    return [caption for _, caption, _, _ in specs]


def upsert_figure_section(body: str, specs: Sequence[FigureSpec]) -> str:
    """把配图并入正文的 `### 图示` 区块：已有则追加，没有则按锚点插入新区块。

    追加而不是覆盖，是因为 `/review` 常常是「原来有一张区域图，这次再补一张换序后的」，
    覆盖会把上次画的图悄悄丢掉。
    """
    block = render_figure_block(specs)
    if not block:
        return body

    match = FIGURE_SECTION_RE.search(body)
    if match:
        existing = match.group(2).strip("\r\n")
        merged = f"{match.group(1)}{existing}\n\n{block}\n\n"
        return body[: match.start()] + merged + body[match.end():]

    new_section = f"{FIGURE_HEADING_LINE}\n{block}\n\n"
    for anchor in FIGURE_ANCHOR_HEADINGS:
        index = body.find(f"\n{anchor}")
        if index != -1:
            insert_at = index + 1
            return body[:insert_at] + new_section + body[insert_at:]
    return body.rstrip() + f"\n\n{new_section}".rstrip() + "\n"


def replace_figure_embeds_for_cli(text: str) -> str:
    """把 svg 嵌入行和 tikz/mermaid 代码块换成一句提示，供 `--plain` 之类的 CLI 预览使用。

    连续多张图只保留一句提示，避免预览被占满。
    """
    if not text:
        return text
    replaced = FIGURE_SOURCE_COMMENT_RE.sub("", text)
    replaced = FIGURE_CODE_BLOCK_RE.sub(CLI_FIGURE_PLACEHOLDER, replaced)
    replaced = FIGURE_EMBED_LINE_RE.sub(CLI_FIGURE_PLACEHOLDER, replaced)
    lines = replaced.splitlines()
    deduped = [
        line
        for index, line in enumerate(lines)
        if line.strip() != CLI_FIGURE_PLACEHOLDER or index == 0 or lines[index - 1].strip() != CLI_FIGURE_PLACEHOLDER
    ]
    return "\n".join(deduped)
