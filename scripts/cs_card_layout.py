"""408 五模块题卡的标题与 Obsidian 折叠块；不存储学习状态。"""

DIAGNOSIS = "精准把脉"
BREAKTHROUGH = "破题密码"
ANALYSIS = "暴力扫雷"
SOP = "提炼 SOP"
VARIANT = "变式拷问"


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
