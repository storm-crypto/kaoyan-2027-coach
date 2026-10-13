"""元技能正文的共享结构。只解析明确的段落，不从公式或中文逗号猜步骤。"""
import re

SECTION_RE = re.compile(r"^(看到什么|怎么做|适用边界|补充例子)：\s*$", re.M)
MATH_RE = re.compile(r"\$\$[\s\S]*?\$\$|(?<!\$)\$(?!\$)(?:\\.|[^$])*?\$(?!\$)")


def split_items(text):
    """显式编号/项目符号为分界，保留项目内部的整块公式和换行。"""
    protected = MATH_RE.sub(lambda m: re.sub(r"[^\n]", " ", m[0]), text)
    starts = list(re.finditer(r"^(?:\d+[.)]|[-*])\s+", protected, re.M))
    if not starts:
        return [text.strip()] if text.strip() else []
    items = []
    prefix = text[:starts[0].start()].strip()
    if prefix:
        items.append(prefix)
    for i, start in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        item = text[start.end():end].strip()
        if item:
            items.append(item)
    return items


def first_arrow(text):
    """旧索引兼容：只取公式与引号之外的箭头，避免切断触发条件或推导。"""
    protected = MATH_RE.sub(lambda m: " " * len(m[0]), text)
    close = []
    pairs = {'「': '」', '『': '』', '“': '”'}
    for i, char in enumerate(protected):
        if char in pairs:
            close.append(pairs[char])
        elif close and char == close[-1]:
            close.pop()
        elif char == '→' and not close:
            return i
    return -1


def parse_decision(text):
    headings = list(SECTION_RE.finditer(text))
    if headings:
        sections = {}
        for i, h in enumerate(headings):
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            sections[h[1]] = text[h.end():end].strip()
        return {'trigger': sections.get('看到什么', ''),
                'steps': split_items(sections.get('怎么做', '')),
                'boundaries': split_items(sections.get('适用边界', '')),
                'examples': split_items(sections.get('补充例子', ''))}
    arrow = first_arrow(text)
    return {'trigger': text[:arrow].strip() if arrow >= 0 else '',
            'steps': [text[arrow + 1:].strip()] if arrow >= 0 else ([text.strip()] if text.strip() else []),
            'boundaries': [], 'examples': []}


def format_decision(trigger, steps, boundaries=(), examples=()):
    out = ['看到什么：', trigger.strip(), '', '怎么做：']
    out += [f'{i}. {step.strip()}' for i, step in enumerate(steps, 1)]
    for title, items in [('适用边界', boundaries), ('补充例子', examples)]:
        if items:
            out += ['', f'{title}：', *[f'- {item.strip()}' for item in items]]
    return '\n'.join(out)


def unmarked_math(text):
    """诊断裸公式；不尝试猜测/自动包裹公式，更不改写数学含义。"""
    plain = MATH_RE.sub(lambda m: ' ' * len(m[0]), text)
    return [m[0] for m in re.finditer(
        r"\\(?:frac|sqrt|sum|int|lim|[a-zA-Z]+)|[A-Za-z][_^]|[A-Za-z][′″]|"
        r"(?:[A-Za-z]+\([^\n（）]*?\))|[√∫∑Σ]|[A-Za-z0-9][=≤≥≠^]", plain)]
