#!/usr/bin/env python3
"""为错题卡生成配图（SVG / TikZ / Mermaid），并在落盘前做「能不能在 Obsidian 里渲染出来」的硬校验。

用法:
  python3 create_figure.py [OBSIDIAN_ROOT]
      --question-id qid-xxxxxxxxxxxx
      --slug [图的短名，用于文件名]
      --caption [图N：一句话说明]
      [--kind svg|tikz|mermaid]  # 默认 svg
      [--index 1]            # 不传则自动续号；同 slug 已存在时自动复用原序号（覆盖）
      [--width 480]          # 卡片中嵌入的显示宽度（仅 svg 有效）
      [--source-file PATH]   # 不传则从 stdin 读源码（--svg-file 是旧别名）
      [--allow-fixed-theme]  # svg：豁免「必须内嵌 prefers-color-scheme」检查
      [--dry-run]            # 只校验不落盘

说明:
- 图落盘到 `错题本/_附图/[qid]/[qid]-[序号]-[slug].{svg|tikz|mmd}`，文件名带 qid 保证全库唯一。
- 返回的 `figure_arg` 可直接原样传给 `create_wrong_card.py --figure` / `update_card.py --figure`。
- svg：Obsidian 以 `<img>` 方式渲染，所以外链资源、<foreignObject>、脚本一律无效或危险，全部拒绝；
  `<text>` 里的 `$...$` 会自动转成 Unicode；上色必须「字面色属性 + CSS 类覆盖」双层写。
- tikz：由 Obsidian 的 TikZJax 插件在打开卡片时编译。本机没有 TeX，编译错误只有打开卡片才看得到，
  所以这里做白名单式静态检查：必须有 \begin{document}、宏包只能用 TikZJax 自带的、不能含中文
  （TikZJax 没有 CJK 字体）、花括号与环境必须配平。
- mermaid：Obsidian 原生渲染。检查图类型声明、节点标签里的非法字符、括号配平，节点过多会告警。
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Tuple

from env_util import atomic_write, json_error, resolve_obsidian_root, sanitize_path_segment
from figure_ops import render_figure_embed
from latex_to_unicode import latex_to_unicode

QUESTION_ID_RE = re.compile(r"^qid-[0-9a-f]{12}$")
SVG_NS = "http://www.w3.org/2000/svg"

FIGURE_DIR_NAME = "_附图"
WRONG_BOOK_DIR_NAME = "错题本"

MAX_FIGURE_BYTES = 32 * 1024
WARN_FIGURE_BYTES = 8 * 1024
MAX_TIKZ_BYTES = 16 * 1024
WARN_TIKZ_BYTES = 4 * 1024
MAX_MERMAID_BYTES = 8 * 1024
WARN_MERMAID_BYTES = 3 * 1024
MAX_MERMAID_NODES = 15
MAX_MERMAID_LINES = 40

FIGURE_KINDS = {"svg": ".svg", "tikz": ".tikz", "mermaid": ".mmd"}
DEFAULT_KIND = "svg"
FENCE_RE = re.compile(r"^\s*```", re.M)
# TikZJax 没有 CJK 字体：中文一律不上图，写进 caption。
CJK_CHAR_RE = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")

# obsidian-tikzjax 自带的宏包；其它 \usepackage 会直接编译失败。
TIKZ_ALLOWED_PACKAGES = {
    "tikz", "pgfplots", "tikz-3dplot", "tikz-cd", "circuitikz", "chemfig", "array",
    "amsmath", "amstext", "amsfonts", "amssymb", "xcolor",
}
# 常用且确认存在于标准 TikZ 发行版的库；不在这里的不拦，只告警。
TIKZ_KNOWN_LIBRARIES = {
    "arrows", "arrows.meta", "calc", "patterns", "patterns.meta", "positioning", "shapes",
    "shapes.geometric", "shapes.misc", "decorations", "decorations.markings",
    "decorations.pathmorphing", "decorations.pathreplacing", "intersections", "angles",
    "quotes", "3d", "backgrounds", "fit", "matrix", "math", "through", "shadings", "fadings",
    "hobby", "bending", "chains", "scopes", "trees", "graphs", "automata", "petri",
}
TIKZ_FORBIDDEN_COMMANDS = {
    "\\documentclass": "TikZJax 自己加 \\documentclass，源码里再写一次会编译失败",
    "\\input": "TikZJax 无法读取外部文件",
    "\\include": "TikZJax 无法读取外部文件",
    "\\write": "错题卡配图不允许写文件",
    "\\openout": "错题卡配图不允许写文件",
    "\\openin": "TikZJax 无法读取外部文件",
    "\\immediate": "错题卡配图不允许 IO 原语",
    "\\catcode": "错题卡配图不允许改 catcode",
}
TIKZ_USEPACKAGE_RE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{([^}]*)\}")
TIKZ_USETIKZLIBRARY_RE = re.compile(r"\\usetikzlibrary\{([^}]*)\}")
TIKZ_ENV_RE = re.compile(r"\\(begin|end)\{([A-Za-z*]+)\}")
TIKZ_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")

MERMAID_DIAGRAM_TYPES = (
    "flowchart", "graph", "sequenceDiagram", "stateDiagram-v2", "stateDiagram", "classDiagram",
    "erDiagram", "gantt", "pie", "journey", "gitGraph", "mindmap", "timeline", "block-beta",
    "xychart-beta", "quadrantChart", "sankey-beta", "packet-beta",
)
MERMAID_FORBIDDEN_PATTERNS = (
    (re.compile(r"^\s*click\s", re.M | re.I), "Mermaid 里禁止 click 交互（错题卡是静态阅读材料，且属于安全面）"),
    (re.compile(r"<script", re.I), "Mermaid 里禁止 <script>"),
    (re.compile(r"javascript:", re.I), "Mermaid 里禁止 javascript: 链接"),
    (re.compile(r"https?://", re.I), "Mermaid 里禁止外链"),
    (re.compile(r"%%\{", re.I), "Mermaid 里禁止 %%{init ...}%% 指令：Obsidian 已按主题处理配色，指令只会把图弄坏"),
)
# 流程图节点标签 [ ... ] 里未加引号的 | 或 ( ) 会被当成语法：`A[PC|out]` 直接解析失败。
MERMAID_UNQUOTED_LABEL_RE = re.compile(r'\[(?!")[^\]"\n]*[|()][^\]"\n]*\]')
MERMAID_NODE_ID_RE = re.compile(r'(?<![\w"])([A-Za-z_][\w]*)(?=\s*(?:\[|\(\(|\(|\{|>))')
MERMAID_EDGE_ID_RE = re.compile(r'(?<![\w"])([A-Za-z_][\w]*)(?=\s*(?:-->|---|-\.->|==>|<--|<-->))')
MERMAID_EDGE_TARGET_RE = re.compile(r"(?:-->|---|-\.->|==>|<-->)\s*(?:\|[^|\n]*\|\s*)?([A-Za-z_][\w]*)")
MIN_FONT_SIZE_PX = 12.0
MIN_FONT_SIZE_PT = 9.0
MIN_EMBED_WIDTH = 200
MAX_EMBED_WIDTH = 900
DEFAULT_EMBED_WIDTH = 480

# Obsidian 用 <img> 渲染 svg：脚本不执行、foreignObject 不显示、外链资源不加载。
FORBIDDEN_TAGS = {
    "script": "SVG 里禁止 <script>（Obsidian 以 <img> 渲染，脚本不会执行，且属于安全面）",
    "foreignObject": "SVG 里禁止 <foreignObject>（<img> 渲染路径下整块内容不显示，是最常见的「图是空白」原因）",
    "iframe": "SVG 里禁止 <iframe>",
    "image": "SVG 里禁止 <image>（嵌位图会让矢量图失去意义，且外链一律加载不出来）",
    "animate": "SVG 里禁止动画元素（错题卡是静态阅读材料）",
    "animateTransform": "SVG 里禁止动画元素（错题卡是静态阅读材料）",
}

GENERIC_FONT_FAMILIES = (
    "sans-serif",
    "serif",
    "monospace",
    "system-ui",
    "ui-sans-serif",
    "ui-serif",
    "ui-monospace",
    "cursive",
    "fantasy",
)

XMLNS_ATTR_RE = re.compile(r"""\sxmlns(?::[A-Za-z0-9_-]+)?\s*=\s*(?P<q>["'])(?:(?!(?P=q)).)*(?P=q)""", re.S)
EXTERNAL_URL_RE = re.compile(r"https?://", re.I)
EVENT_ATTR_RE = re.compile(r"\son[a-z]+\s*=", re.I)
CSS_IMPORT_RE = re.compile(r"@import", re.I)
TEXT_ELEMENT_RE = re.compile(r"(<text\b[^>]*>)(.*?)(</text>)", re.S | re.I)
FONT_SIZE_RE = re.compile(r"""font-size\s*[:=]\s*["']?\s*(\d+(?:\.\d+)?)\s*(px|pt|em|rem|%)?""", re.I)
# 属性写法 font-family="A, sans-serif" 与 CSS 写法 font-family: "A", sans-serif 的终止符不同，分开匹配。
FONT_FAMILY_ATTR_RE = re.compile(r"""font-family\s*=\s*(?P<q>["'])(?P<value>(?:(?!(?P=q)).)*)(?P=q)""", re.S | re.I)
FONT_FAMILY_CSS_RE = re.compile(r"font-family\s*:\s*(?P<value>[^;}\n]+)", re.I)
LEFTOVER_LATEX_RE = re.compile(r"\\[A-Za-z]{2,}|\$")
# 上色属性里写 var(...) 是「整张图变黑块」的头号成因：不支持 CSS 自定义属性的渲染器会
# 判定整个属性值无效，fill 回落成默认黑、stroke 回落成 none。正确写法是字面色写在
# presentation attribute 上、CSS 类再用 var() 覆盖（CSS 优先级高于 presentation attribute），
# 这样支持 var() 的环境走主题色，不支持的环境仍是一张浅色可读图。
PAINT_ATTRIBUTES = ("fill", "stroke", "stop-color", "flood-color", "lighting-color", "color")
PAINT_ATTR_VAR_RE = re.compile(
    r"""\s(?P<attr>fill|stroke|stop-color|flood-color|lighting-color|color)\s*=\s*["']\s*var\(""",
    re.I,
)
PAINTABLE_TAGS = {
    "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan", "g", "use",
}
INDEXED_FILENAME_RE = re.compile(r"^qid-[0-9a-f]{12}-(\d{2})-(.+)$")


def looks_like_obsidian_root_arg(token: str) -> bool:
    candidate = Path(token).expanduser()
    return (
        candidate.exists()
        or candidate.is_absolute()
        or token in {".", ".."}
        or token.startswith(("~/", "./", "../"))
        or "/" in token
        or "\\" in token
    )


def parse_args() -> Tuple[Path, argparse.Namespace]:
    raw_args = sys.argv[1:]
    obsidian_root_arg = None
    if raw_args and not raw_args[0].startswith("--") and looks_like_obsidian_root_arg(raw_args[0]):
        obsidian_root_arg = raw_args[0]
        raw_args = raw_args[1:]

    parser = argparse.ArgumentParser(description="生成并校验错题卡配图（SVG / TikZ / Mermaid）")
    parser.add_argument("--question-id", required=True, help="所属错题卡主键 qid-xxxxxxxxxxxx")
    parser.add_argument("--slug", required=True, help="图的短名，用于文件名，如 积分区域")
    parser.add_argument("--caption", required=True, help="图的说明，如 图1：原积分区域 D 与条带方向")
    parser.add_argument("--kind", choices=sorted(FIGURE_KINDS), default=DEFAULT_KIND, help="图源类型，默认 svg")
    parser.add_argument("--index", type=int, help="图序号；不传则自动续号")
    parser.add_argument("--width", type=int, default=DEFAULT_EMBED_WIDTH, help="卡片中的嵌入显示宽度（仅 svg）")
    parser.add_argument("--source-file", help="图源码文件路径；不传则从 stdin 读")
    parser.add_argument("--svg-file", dest="source_file", help=argparse.SUPPRESS)
    parser.add_argument(
        "--allow-fixed-theme",
        action="store_true",
        help="svg：豁免「必须内嵌 prefers-color-scheme 自适应配色」检查",
    )
    parser.add_argument("--dry-run", action="store_true", help="只校验不落盘")
    args = parser.parse_args(raw_args)
    return resolve_obsidian_root(obsidian_root_arg), args


def read_figure_source(source_file: Optional[str], kind: str) -> str:
    if source_file:
        path = Path(source_file).expanduser()
        if not path.is_file():
            json_error(f"--source-file 不存在: {path}")
        return path.read_text(encoding="utf-8")
    if sys.stdin.isatty():
        json_error(f"未提供 {kind} 源码：请传 --source-file，或用 heredoc 从 stdin 输入")
    return sys.stdin.read()


def strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def convert_latex_in_text_elements(svg_source: str) -> Tuple[str, int]:
    """把 <text> 正文里的 `$...$` 就地转成 Unicode。

    SVG 不渲染 LaTeX，模型写惯了 `$x^2$` 会直接把美元符号画到图上。这里做无损兜底，
    比硬报错少一轮往返；转不掉的残留（裸 `\\frac` 之类）再由 validate 拦下。
    """
    converted = 0

    def _replace(match: re.Match) -> str:
        nonlocal converted
        open_tag, body, close_tag = match.group(1), match.group(2), match.group(3)
        if "$" not in body:
            return match.group(0)
        # 只转标签之间的文本，保留内部 <tspan> 等子标签结构
        def _convert_chunk(chunk_match: re.Match) -> str:
            nonlocal converted
            chunk = chunk_match.group(0)
            if "$" not in chunk:
                return chunk
            new_chunk = latex_to_unicode(chunk)
            if new_chunk != chunk:
                converted += 1
            return new_chunk

        new_body = re.sub(r"(?:(?!<)[\s\S])+", _convert_chunk, body)
        return f"{open_tag}{new_body}{close_tag}"

    return TEXT_ELEMENT_RE.sub(_replace, svg_source), converted


def collect_text_contents(root: ET.Element) -> List[str]:
    contents = []
    for element in root.iter():
        if strip_namespace(element.tag) in {"text", "tspan"}:
            for chunk in (element.text, element.tail):
                if chunk and chunk.strip():
                    contents.append(chunk.strip())
    return contents


def validate_structure(svg_source: str) -> ET.Element:
    try:
        root = ET.fromstring(svg_source)
    except ET.ParseError as exc:
        json_error(f"SVG 不是合法 XML，无法解析: {exc}")

    if strip_namespace(root.tag) != "svg":
        json_error(f"根元素必须是 <svg>，实际是 <{strip_namespace(root.tag)}>")
    if not root.get("viewBox"):
        json_error("<svg> 缺少 viewBox：没有 viewBox 时 Obsidian 里的缩放行为不可控，图会被裁或糊掉")
    return root


def validate_forbidden_elements(root: ET.Element) -> None:
    for element in root.iter():
        tag = strip_namespace(element.tag)
        if tag in FORBIDDEN_TAGS:
            json_error(FORBIDDEN_TAGS[tag])
        for attr_name in element.attrib:
            if strip_namespace(attr_name).lower().startswith("on"):
                json_error(f"SVG 里禁止事件属性: {attr_name}")


def validate_no_external_refs(svg_source: str) -> None:
    scrubbed = XMLNS_ATTR_RE.sub(" ", svg_source)
    if EXTERNAL_URL_RE.search(scrubbed):
        json_error(
            "SVG 里禁止任何外链资源（http/https）：Obsidian 以 <img> 渲染，"
            "外部图片/字体/样式一律加载不出来，落盘就是残图"
        )
    if CSS_IMPORT_RE.search(scrubbed):
        json_error("SVG 里禁止 @import：外部样式在 <img> 渲染路径下不生效")
    if EVENT_ATTR_RE.search(scrubbed):
        json_error("SVG 里禁止事件属性（on*=）")


def validate_fonts(svg_source: str) -> None:
    for match in FONT_SIZE_RE.finditer(svg_source):
        value = float(match.group(1))
        unit = (match.group(2) or "px").lower()
        if unit == "px" and value < MIN_FONT_SIZE_PX:
            json_error(
                f"字号过小: font-size {match.group(1)}{unit}。卡片里图会被缩到 480px 左右，"
                f"字号请 ≥ {int(MIN_FONT_SIZE_PX)}px，否则标注糊成一团"
            )
        if unit == "pt" and value < MIN_FONT_SIZE_PT:
            json_error(f"字号过小: font-size {match.group(1)}pt，请 ≥ {int(MIN_FONT_SIZE_PT)}pt")

    for pattern in (FONT_FAMILY_ATTR_RE, FONT_FAMILY_CSS_RE):
        for match in pattern.finditer(svg_source):
            declaration = match.group("value").lower()
            if not any(generic in declaration for generic in GENERIC_FONT_FAMILIES):
                json_error(
                    f"font-family 缺少通用兜底字体: {match.group('value').strip()}。"
                    "请在末尾补 sans-serif / serif / monospace，换设备才不会掉字"
                )


def validate_text_is_unicode(root: ET.Element) -> None:
    for content in collect_text_contents(root):
        if LEFTOVER_LATEX_RE.search(content):
            json_error(
                f"图中文本仍含未转写的 LaTeX: 「{content}」。"
                "SVG 不渲染 LaTeX，请直接写 Unicode（如 x², ∫, ≤, π, α）"
            )


def validate_paint_fallbacks(svg_source: str, root: ET.Element) -> List[str]:
    """确保图在不支持 CSS 自定义属性的渲染器里也不会变成一个黑块。

    硬拦 `fill="var(--x)"` 这种写法；对「只靠 CSS 类上色、元素上没有字面兜底色」的
    元素给出告警——它们在这类渲染器里会消失或涂黑。
    """
    match = PAINT_ATTR_VAR_RE.search(svg_source)
    if match:
        attr = match.group("attr")
        json_error(
            f'{attr}="var(...)" 不安全：不支持 CSS 自定义属性的渲染器会判定整个属性值无效，'
            f"{attr} 回落成默认值（fill 变黑、stroke 变无），整张图会糊成一个黑块。"
            f'请改成双层写法：元素上写字面色 {attr}="#1f2933"，再用 CSS 类 .ink{{{attr}:var(--ink)}} 覆盖。'
            "详见 references/svg-figure-guide.md 的通用骨架"
        )

    if "var(" not in svg_source:
        return []

    unpainted: List[str] = []

    def walk(element: ET.Element, has_fill: bool, has_stroke: bool) -> None:
        tag = strip_namespace(element.tag)
        own_fill = has_fill or bool(element.get("fill"))
        own_stroke = has_stroke or bool(element.get("stroke"))
        if tag in PAINTABLE_TAGS and tag not in {"g", "use"} and not own_fill and not own_stroke:
            if len(unpainted) < 3:
                unpainted.append(f"<{tag}>")
        for child in element:
            walk(child, own_fill, own_stroke)

    walk(root, False, False)
    if unpainted:
        return [
            f"以下元素只靠 CSS 类上色、没有字面兜底色：{'、'.join(unpainted)}。"
            "在不支持 CSS 变量的渲染器里它们会消失或涂黑，建议补上 fill/stroke 属性"
        ]
    return []


def validate_theme_adaptive(svg_source: str, allow_fixed_theme: bool) -> None:
    if allow_fixed_theme:
        return
    if "prefers-color-scheme" not in svg_source:
        json_error(
            "SVG 未内嵌深色模式适配：请按 references/svg-figure-guide.md 的配色骨架，"
            "在 <style> 里用 CSS 变量 + @media (prefers-color-scheme: dark) 定义深浅两套色。"
            "确需固定配色时显式加 --allow-fixed-theme"
        )


def validate_size(svg_source: str) -> List[str]:
    size = len(svg_source.encode("utf-8"))
    if size > MAX_FIGURE_BYTES:
        json_error(
            f"SVG 体积 {size} 字节，超过上限 {MAX_FIGURE_BYTES}。"
            "图太复杂说明它在替解法讲话，请拆成两张，或只保留决定解法的那几个要素"
        )
    warnings = []
    if size > WARN_FIGURE_BYTES:
        warnings.append(f"SVG 体积 {size} 字节偏大，考虑拆成两张更聚焦的图")
    return warnings


def validate_caption(caption: str) -> List[str]:
    text = caption.strip()
    if not text:
        json_error("--caption 不能为空：图必须有一句说明，复习时才知道该看图的哪里")
    if "|" in text:
        json_error("--caption 里不能含 `|`：该字符是 --figure 参数的分隔符")
    if "[[" in text or "]]" in text:
        json_error("--caption 里不能含 `[[` / `]]`")
    warnings = []
    if not text.startswith("图"):
        warnings.append("建议 caption 以「图1：」「图2：」开头，方便规范解法里用「见图1」引用")
    return warnings


def validate_width(width: int) -> None:
    if not MIN_EMBED_WIDTH <= width <= MAX_EMBED_WIDTH:
        json_error(f"--width 需在 {MIN_EMBED_WIDTH}~{MAX_EMBED_WIDTH} 之间，实际 {width}")


def validate_no_fence(source: str, kind: str) -> None:
    if FENCE_RE.search(source):
        json_error(
            f"{kind} 源码里不要带 ``` 围栏：只传代码块内部的内容，围栏由建卡脚本按图源类型自动加"
        )


def validate_brace_balance(source: str, kind: str) -> None:
    """花括号 / 环境不配平是 TikZ 最常见的编译失败原因，而本机没有 TeX 可以预编译。"""
    stripped = TIKZ_COMMENT_RE.sub("", source).replace("\\{", "").replace("\\}", "")
    depth = 0
    for char in stripped:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                json_error(f"{kind} 源码花括号不配平：出现了多余的 `}}`")
    if depth != 0:
        json_error(f"{kind} 源码花括号不配平：有 {depth} 个 `{{` 没有闭合")


def validate_tikz(source: str) -> List[str]:
    validate_no_fence(source, "tikz")
    if "\\begin{document}" not in source or "\\end{document}" not in source:
        json_error(
            "TikZ 源码必须包含 \\begin{document} ... \\end{document}：obsidian-tikzjax 要求这个结构，"
            "宏包与库声明写在 \\begin{document} 之前"
        )
    if "\\begin{tikzpicture}" not in source:
        json_error("TikZ 源码里没有 \\begin{tikzpicture}")
    for command, reason in TIKZ_FORBIDDEN_COMMANDS.items():
        if re.search(re.escape(command) + r"(?![A-Za-z])", source):
            json_error(f"TikZ 源码里禁止 {command}：{reason}")

    cjk = CJK_CHAR_RE.search(TIKZ_COMMENT_RE.sub("", source))
    if cjk:
        json_error(
            f"TikZ 源码里含中文字符「{cjk.group(0)}」：TikZJax 没有 CJK 字体，会渲染成空白或方块。"
            "图内只写英文与数学符号，中文说明放进 --caption"
        )

    for match in TIKZ_USEPACKAGE_RE.finditer(source):
        for package in (name.strip() for name in match.group(1).split(",")):
            if package and package not in TIKZ_ALLOWED_PACKAGES:
                json_error(
                    f"TikZ 宏包 {package} 不在 TikZJax 自带列表里，会编译失败。"
                    f"可用: {', '.join(sorted(TIKZ_ALLOWED_PACKAGES))}"
                )

    validate_brace_balance(source, "tikz")

    stack: List[str] = []
    for match in TIKZ_ENV_RE.finditer(TIKZ_COMMENT_RE.sub("", source)):
        action, env = match.group(1), match.group(2)
        if action == "begin":
            stack.append(env)
        else:
            if not stack or stack[-1] != env:
                expected = stack[-1] if stack else "（无）"
                json_error(f"TikZ 环境不配平：遇到 \\end{{{env}}}，但当前打开的是 {expected}")
            stack.pop()
    if stack:
        json_error(f"TikZ 环境不配平：{', '.join(stack)} 没有 \\end")

    warnings: List[str] = []
    size = len(source.encode("utf-8"))
    if size > MAX_TIKZ_BYTES:
        json_error(f"TikZ 源码 {size} 字节，超过上限 {MAX_TIKZ_BYTES}。图太复杂说明它在替解法讲话，请拆或减")
    if size > WARN_TIKZ_BYTES:
        warnings.append(f"TikZ 源码 {size} 字节偏大，TikZJax 首次编译会明显变慢，考虑精简")
    for match in TIKZ_USETIKZLIBRARY_RE.finditer(source):
        for lib in (name.strip() for name in match.group(1).split(",")):
            if lib and lib not in TIKZ_KNOWN_LIBRARIES:
                warnings.append(f"TikZ 库 {lib} 不在常用列表里，请在 Obsidian 里确认能编译")
    uses_pgfplots = "\\usepackage{pgfplots}" in source
    if uses_pgfplots and "\\pgfplotsset{compat=" not in source:
        warnings.append("用了 pgfplots 但没写 \\pgfplotsset{compat=1.16}，坐标轴和图例行为会不稳定")
    if uses_pgfplots and "\\begin{axis}" not in source:
        warnings.append("引入了 pgfplots 但没有 \\begin{axis}，如果只是手画 TikZ 可以去掉这个宏包")
    if "\\usepackage{tikz-3dplot}" in source and "\\tdplotsetmaincoords" not in source:
        warnings.append("引入了 tikz-3dplot 但没调用 \\tdplotsetmaincoords{θ}{φ}，三维视角会退化成平面")
    return warnings


def mermaid_diagram_type(source: str) -> str:
    for line in source.splitlines():
        text = line.strip()
        if not text or text.startswith("%%"):
            continue
        return text.split()[0]
    return ""


def validate_bracket_balance(source: str) -> None:
    pairs = {"[": "]", "(": ")", "{": "}"}
    closers = set(pairs.values())
    for line in source.splitlines():
        if line.strip().startswith("%%"):
            continue
        stack: List[str] = []
        in_quote = False
        for char in line:
            if char == '"':
                in_quote = not in_quote
                continue
            if in_quote:
                continue
            if char in pairs:
                stack.append(char)
            elif char in closers:
                if not stack or pairs[stack[-1]] != char:
                    json_error(f"Mermaid 源码括号不配平：多余的 `{char}`（行: {line.strip()}）")
                stack.pop()
        if stack:
            json_error(f"Mermaid 源码括号不配平：`{stack[-1]}` 没有闭合（行: {line.strip()}）")


def validate_mermaid(source: str) -> List[str]:
    validate_no_fence(source, "mermaid")
    diagram = mermaid_diagram_type(source)
    if diagram not in MERMAID_DIAGRAM_TYPES:
        json_error(
            f"Mermaid 第一行必须声明图类型（如 flowchart LR / graph TD / sequenceDiagram / stateDiagram-v2），"
            f"实际是: {diagram or '（空）'}"
        )
    for pattern, reason in MERMAID_FORBIDDEN_PATTERNS:
        if pattern.search(source):
            json_error(reason)
    if diagram in {"flowchart", "graph"}:
        bad = MERMAID_UNQUOTED_LABEL_RE.search(source)
        if bad:
            json_error(
                f"Mermaid 节点标签 {bad.group(0)} 里的 | 或括号没有加引号，会解析失败。"
                '写成 A["PC (out)"] 这种带引号的形式'
            )
    validate_bracket_balance(source)

    warnings: List[str] = []
    size = len(source.encode("utf-8"))
    if size > MAX_MERMAID_BYTES:
        json_error(f"Mermaid 源码 {size} 字节，超过上限 {MAX_MERMAID_BYTES}。图太复杂说明它在替解法讲话，请拆")
    if size > WARN_MERMAID_BYTES:
        warnings.append(f"Mermaid 源码 {size} 字节偏大，考虑拆成两张")
    lines = [line for line in source.splitlines() if line.strip() and not line.strip().startswith("%%")]
    if len(lines) > MAX_MERMAID_LINES:
        warnings.append(f"Mermaid 有 {len(lines)} 行，超过 {MAX_MERMAID_LINES} 行的图在卡片里基本读不了，建议拆")
    if diagram in {"flowchart", "graph"}:
        ids = set(MERMAID_NODE_ID_RE.findall(source)) | set(MERMAID_EDGE_ID_RE.findall(source))
        ids |= set(MERMAID_EDGE_TARGET_RE.findall(source))
        ids -= {"subgraph", "end", "direction", "style", "classDef", "class", "linkStyle", diagram}
        if len(ids) > MAX_MERMAID_NODES:
            warnings.append(
                f"Mermaid 约有 {len(ids)} 个节点，超过 {MAX_MERMAID_NODES}：只画本题经过的局部链路，别画全景"
            )
    if "$" in source:
        warnings.append("Mermaid 标签里有 $：Obsidian 的 Mermaid 不渲染 LaTeX，控制信号与变量请写纯文本（如 PCout=1）")
    return warnings


def validate_svg(svg_source: str, allow_fixed_theme: bool) -> Tuple[str, List[str]]:
    svg_source, converted_count = convert_latex_in_text_elements(svg_source)
    root = validate_structure(svg_source)
    validate_forbidden_elements(root)
    validate_no_external_refs(svg_source)
    validate_fonts(svg_source)
    validate_text_is_unicode(root)
    validate_theme_adaptive(svg_source, allow_fixed_theme)
    warnings = validate_size(svg_source) + validate_paint_fallbacks(svg_source, root)
    if converted_count:
        warnings.append(f"已自动把 {converted_count} 处 LaTeX 文本转写成 Unicode，请在 Obsidian 里确认转写结果")
    return svg_source, warnings


def figure_dir_for(obsidian_root: Path, question_id: str) -> Path:
    return Path(obsidian_root) / WRONG_BOOK_DIR_NAME / FIGURE_DIR_NAME / question_id


def resolve_index(figure_dir: Path, question_id: str, slug: str, explicit_index: Optional[int]) -> int:
    """决定图的序号：显式 > 同 slug 复用（覆盖重画）> 自动续号。"""
    if explicit_index is not None:
        if not 1 <= explicit_index <= 99:
            json_error(f"--index 需在 1~99 之间，实际 {explicit_index}")
        return explicit_index

    used_indexes = []
    if figure_dir.is_dir():
        for existing in figure_dir.iterdir():
            if existing.suffix.lower() not in FIGURE_KINDS.values():
                continue
            match = INDEXED_FILENAME_RE.match(existing.stem)
            if not match:
                continue
            if match.group(2) == slug:
                return int(match.group(1))
            used_indexes.append(int(match.group(1)))
    return max(used_indexes, default=0) + 1


def main() -> None:
    obsidian_root, args = parse_args()
    if not QUESTION_ID_RE.match(args.question_id):
        json_error(f"question_id 格式非法: {args.question_id}")

    slug = sanitize_path_segment(args.slug)
    kind = args.kind
    validate_width(args.width)
    caption_warnings = validate_caption(args.caption)

    source = read_figure_source(args.source_file, kind).strip()
    if not source:
        json_error(f"{kind} 源码为空")

    if kind == "svg":
        source, kind_warnings = validate_svg(source, args.allow_fixed_theme)
    elif kind == "tikz":
        kind_warnings = validate_tikz(source)
    else:
        kind_warnings = validate_mermaid(source)
    warnings = kind_warnings + caption_warnings
    if kind != "svg" and args.width != DEFAULT_EMBED_WIDTH:
        warnings.append(f"--width 只对 svg 有效，{kind} 代码块由 Obsidian 自适应宽度，已忽略")

    figure_dir = figure_dir_for(obsidian_root, args.question_id)
    index = resolve_index(figure_dir, args.question_id, slug, args.index)
    filename = f"{args.question_id}-{index:02d}-{slug}{FIGURE_KINDS[kind]}"
    relative_path = f"{WRONG_BOOK_DIR_NAME}/{FIGURE_DIR_NAME}/{args.question_id}/{filename}"
    output_path = figure_dir / filename

    if not args.dry_run:
        figure_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(output_path, source + "\n")

    caption = args.caption.strip()
    # 非默认宽度必须带进 figure_arg，否则模型把它粘给 --figure 时宽度会被静默丢回 480。
    figure_arg = f"{relative_path}|{caption}"
    if kind == "svg" and args.width != DEFAULT_EMBED_WIDTH:
        figure_arg = f"{figure_arg}|{args.width}"

    print(json.dumps({
        "path": str(output_path),
        "relative_path": relative_path,
        "kind": kind,
        "embed": render_figure_embed(relative_path, args.width, source),
        "figure_arg": figure_arg,
        "question_id": args.question_id,
        "index": index,
        "slug": slug,
        "caption": caption,
        "bytes": len(source.encode("utf-8")),
        "dry_run": args.dry_run,
        "warnings": warnings,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
