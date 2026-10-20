"""408 题卡的展示标题与兼容读取；不存储学习状态。"""

import re

DIAGNOSIS = "精准把脉"
BREAKTHROUGH = "破题密码"
ANALYSIS = "暴力扫雷"
SOP = "提炼 SOP"
VARIANT = "变式拷问"

PURPOSES = {
    DIAGNOSIS: "结论、考点与错因",
    BREAKTHROUGH: "题眼、原理与第一步",
    ANALYSIS: "逐项判断或逐问解答",
    SOP: "考场动作与长期规则",
    VARIANT: "独立作答，检验迁移",
    "图示": "辅助理解过程",
}
PENDING_VARIANT = "**变式状态：** 待作答"


def heading_name(name: str) -> str:
    return f"{name}（{PURPOSES[name]}）" if name in PURPOSES else name


def module_span(text: str, name: str, level: int = 3):
    """读取带用途或旧版标题的区块；代码围栏内的同名标题不是区块边界。"""
    headings = []
    offset = 0
    fence = ""
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        if fence:
            if re.fullmatch(r"[ \t]{0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*", stripped):
                fence = ""
        else:
            opening = re.match(r"^[ \t]{0,3}(`{3,}|~{3,})", stripped)
            if opening:
                fence = opening.group(1)
            else:
                heading = re.match(r"^(#{1,6}) (.+)$", stripped)
                if heading and len(heading.group(1)) <= level:
                    headings.append((offset, offset + len(line), heading.group(2).strip(), len(heading.group(1))))
        offset += len(line)
    matches = []
    pattern = re.compile(re.escape(name) + r"(?:（[^）\n]*）|\([^\)\n]*\))?$")
    for index, (start, content, title, heading_level) in enumerate(headings):
        if heading_level == level and pattern.fullmatch(title):
            end = headings[index + 1][0] if index + 1 < len(headings) else len(text)
            matches.append((start, content, end))
    return matches[0] if len(matches) == 1 else None


def extract_module(text: str, name: str, level: int = 3) -> str:
    span = module_span(text, name, level)
    return text[span[1]:span[2]].strip() if span else ""


def replace_module(text: str, name: str, content: str, level: int = 3) -> str:
    span = module_span(text, name, level)
    if span is None:
        raise ValueError(f"缺少或存在重复的题卡模块：{name}")
    return text[:span[1]] + "\n" + content.strip() + "\n\n" + text[span[2]:]


def folded_callout(text: str, title: str) -> str:
    """用 Obsidian 原生折叠 callout 保留 Markdown、代码和公式。"""
    quoted = "\n".join("> " + line if line else ">" for line in text.strip().splitlines())
    return f"> [!note]- {title}\n>\n{quoted}"


def unfold_callout(text: str) -> str:
    """只去掉最外层 callout；内层引用、列表和代码缩进保持原样。"""
    lines = text.strip().splitlines()
    if not lines or not lines[0].startswith("> [!"):
        return text.strip()
    result = []
    for line in lines[1:]:
        if line.startswith("> "):
            result.append(line[2:])
        elif line == ">":
            result.append("")
        else:
            result.append(line)
    return "\n".join(result).strip()
