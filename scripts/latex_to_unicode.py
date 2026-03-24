#!/usr/bin/env python3
"""将 LaTeX 数学公式转为 Unicode 可读文本，供 CLI 环境下阅读。

仅做保守转写：
- 优先保证“不转错”，其次才是“尽量美观”
- 常见考研数学公式会转成更适合对话框阅读的文本
- 复杂或不支持的命令会尽量保留原意，而不是强行展开
"""
import re
from typing import List, Match, Tuple

# ---------- 希腊字母 ----------
_GREEK = {
    "alpha": "\u03b1", "beta": "\u03b2", "gamma": "\u03b3", "delta": "\u03b4",
    "epsilon": "\u03b5", "varepsilon": "\u03b5", "zeta": "\u03b6", "eta": "\u03b7",
    "theta": "\u03b8", "vartheta": "\u03d1", "iota": "\u03b9", "kappa": "\u03ba",
    "lambda": "\u03bb", "mu": "\u03bc", "nu": "\u03bd", "xi": "\u03be",
    "pi": "\u03c0", "rho": "\u03c1", "sigma": "\u03c3", "tau": "\u03c4",
    "upsilon": "\u03c5", "phi": "\u03c6", "varphi": "\u03c6", "chi": "\u03c7",
    "psi": "\u03c8", "omega": "\u03c9",
    "Gamma": "\u0393", "Delta": "\u0394", "Theta": "\u0398", "Lambda": "\u039b",
    "Xi": "\u039e", "Pi": "\u03a0", "Sigma": "\u03a3", "Phi": "\u03a6",
    "Psi": "\u03a8", "Omega": "\u03a9",
}

# ---------- 上标 / 下标映射 ----------
_SUP = str.maketrans(
    "0123456789+-=()nixy",
    "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079\u207a\u207b\u207c\u207d\u207e\u207f\u2071\u02e3\u02b8",
)
_SUB = str.maketrans(
    "0123456789+-=()aeinoruvx",
    "\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089\u208a\u208b\u208c\u208d\u208e\u2090\u2091\u1d62\u2099\u2092\u1d63\u1d64\u1d65\u2093",
)

# ---------- 简单符号替换 ----------
_NAMED_SYMBOLS = {
    "cdot": "\u00b7",
    "times": "\u00d7",
    "div": "\u00f7",
    "pm": "\u00b1",
    "mp": "\u2213",
    "leq": "\u2264", "le": "\u2264",
    "geq": "\u2265", "ge": "\u2265",
    "neq": "\u2260", "ne": "\u2260",
    "approx": "\u2248",
    "equiv": "\u2261",
    "sim": "\u223c",
    "propto": "\u221d",
    "infty": "\u221e",
    "partial": "\u2202",
    "nabla": "\u2207",
    "forall": "\u2200",
    "exists": "\u2203",
    "in": "\u2208",
    "notin": "\u2209",
    "subset": "\u2282",
    "supset": "\u2283",
    "cup": "\u222a",
    "cap": "\u2229",
    "emptyset": "\u2205",
    "to": "\u2192",
    "rightarrow": "\u2192",
    "leftarrow": "\u2190",
    "Rightarrow": "\u21d2",
    "implies": "\u21d2",
    "Leftarrow": "\u21d0",
    "Leftrightarrow": "\u21d4",
    "iff": "\u21d4",
    "ldots": "\u2026",
    "cdots": "\u22ef",
    "dots": "\u2026",
    "prime": "\u2032",
}

_TOKEN_SYMBOLS = {
    r"\,": " ",
    r"\;": " ",
    r"\!": "",
    r"\%": "%",
    r"\\": " ",
}

# ---------- 大运算符 ----------
_BIG_OPS = {
    "sum": "\u2211",
    "prod": "\u220f",
    "int": "\u222b",
    "iint": "\u222c",
    "iiint": "\u222d",
    "oint": "\u222e",
    "bigcup": "\u22c3",
    "bigcap": "\u22c2",
}

# ---------- 函数名 ----------
_FUNC_NAMES = {
    "sin", "cos", "tan", "cot", "sec", "csc",
    "arcsin", "arccos", "arctan",
    "sinh", "cosh", "tanh",
    "ln", "log", "exp", "lim", "max", "min",
    "sup", "inf", "det", "dim", "ker", "deg",
    "gcd", "arg",
}

_TEXT_COMMANDS = {"text", "mathrm", "textbf", "mathbf", "mathit", "operatorname"}
_IGNORED_COMMANDS = {"displaystyle", "textstyle", "scriptstyle", "scriptscriptstyle", "limits", "nolimits"}
_ACCENT_COMMANDS = {
    "overline": "\u0304",
    "hat": "\u0302",
    "vec": "\u20d7",
}
_DELIMITER_COMMANDS = {
    r"\{": "{",
    r"\}": "}",
    r"\langle": "\u27e8",
    r"\rangle": "\u27e9",
    r"\lvert": "|",
    r"\rvert": "|",
    r"\lfloor": "\u230a",
    r"\rfloor": "\u230b",
    r"\lceil": "\u2308",
    r"\rceil": "\u2309",
}
_LATEX_BLOCK_RE = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$", re.S)


def _skip_spaces(text: str, start: int) -> int:
    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _consume_group(text: str, start: int, open_char: str, close_char: str) -> Tuple[str, int]:
    if start >= len(text) or text[start] != open_char:
        return "", start

    depth = 1
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
        index += 1

    return text[start + 1:], len(text)


def _consume_command_token(text: str, start: int) -> Tuple[str, int]:
    if start >= len(text) or text[start] != "\\":
        return "", start

    if start + 1 < len(text) and text[start + 1].isalpha():
        index = start + 2
        while index < len(text) and text[index].isalpha():
            index += 1
        return text[start:index], index

    if start + 1 < len(text):
        return text[start:start + 2], start + 2

    return text[start:], len(text)


def _consume_argument(text: str, start: int) -> Tuple[str, int]:
    index = _skip_spaces(text, start)
    if index >= len(text):
        return "", index

    if text[index] == "{":
        return _consume_group(text, index, "{", "}")

    if text[index] == "[":
        return _consume_group(text, index, "[", "]")

    if text[index] == "\\":
        token, next_index = _consume_command_token(text, index)
        return token, next_index

    return text[index], index + 1


def _consume_delimiter(text: str, start: int) -> Tuple[str, int]:
    index = _skip_spaces(text, start)
    if index >= len(text):
        return "", index

    for token, value in sorted(_DELIMITER_COMMANDS.items(), key=lambda item: len(item[0]), reverse=True):
        if text.startswith(token, index):
            return value, index + len(token)

    char = text[index]
    if char in "()[]|":
        return char, index + 1
    if char == ".":
        return "", index + 1
    return "", index


def _is_simple_atom(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    return not any(char.isspace() or char in "+-*/=<>≤≥≠()[]{}" for char in value)


def _format_fraction(numerator: str, denominator: str) -> str:
    num = numerator.strip() or "?"
    den = denominator.strip() or "?"
    if not _is_simple_atom(num):
        num = f"({num})"
    if not _is_simple_atom(den):
        den = f"({den})"
    return f"{num}/{den}"


def _format_accent(base: str, accent: str) -> str:
    cleaned = base.strip() or "?"
    if len(cleaned) == 1 or _is_simple_atom(cleaned):
        return cleaned + accent
    return f"({cleaned}){accent}"


def _format_script(content: str, superscript: bool) -> str:
    value = content.strip()
    if not value:
        return ""

    converted = value.translate(_SUP if superscript else _SUB)
    if converted != value:
        return converted

    marker = "^" if superscript else "_"
    if len(value) == 1:
        return marker + value
    return f"{marker}({value})"


def _normalize_result(text: str) -> str:
    result = re.sub(r"[ \t]+", " ", text)
    result = re.sub(r" ?\n ?", "\n", result)
    return result.strip()


def _convert_inner(tex: str) -> str:  # noqa: C901
    """将单个 LaTeX 数学表达式（不含 $ 定界符）转为 Unicode。"""
    pieces: List[str] = []
    index = 0

    while index < len(tex):
        char = tex[index]

        if char == "\\":
            if tex.startswith(r"\left", index):
                delimiter, index = _consume_delimiter(tex, index + len(r"\left"))
                if delimiter:
                    pieces.append(delimiter)
                continue

            if tex.startswith(r"\right", index):
                delimiter, index = _consume_delimiter(tex, index + len(r"\right"))
                if delimiter:
                    pieces.append(delimiter)
                continue

            handled_frac = False
            for command in (r"\dfrac", r"\tfrac", r"\frac"):
                if tex.startswith(command, index):
                    numerator_raw, next_index = _consume_argument(tex, index + len(command))
                    denominator_raw, next_index = _consume_argument(tex, next_index)
                    pieces.append(
                        _format_fraction(
                            _convert_inner(numerator_raw),
                            _convert_inner(denominator_raw),
                        )
                    )
                    index = next_index
                    handled_frac = True
                    break
            if handled_frac:
                continue

            if tex.startswith(r"\sqrt", index):
                next_index = index + len(r"\sqrt")
                root_raw = ""
                next_index = _skip_spaces(tex, next_index)
                if next_index < len(tex) and tex[next_index] == "[":
                    root_raw, next_index = _consume_group(tex, next_index, "[", "]")
                body_raw, next_index = _consume_argument(tex, next_index)
                body = _convert_inner(body_raw)
                if root_raw:
                    root = _format_script(_convert_inner(root_raw), superscript=True)
                    pieces.append(f"{root}\u221a({body})")
                else:
                    pieces.append(f"\u221a({body})")
                index = next_index
                continue

            token, next_index = _consume_command_token(tex, index)
            command = token[1:]

            if token in _TOKEN_SYMBOLS:
                pieces.append(_TOKEN_SYMBOLS[token])
                index = next_index
                continue

            if command in _TEXT_COMMANDS:
                group_raw, next_index = _consume_argument(tex, next_index)
                pieces.append(group_raw)
                index = next_index
                continue

            if command in _ACCENT_COMMANDS:
                base_raw, next_index = _consume_argument(tex, next_index)
                pieces.append(_format_accent(_convert_inner(base_raw), _ACCENT_COMMANDS[command]))
                index = next_index
                continue

            if command in _IGNORED_COMMANDS:
                index = next_index
                continue

            if command in _GREEK:
                pieces.append(_GREEK[command])
                index = next_index
                continue

            if command in _BIG_OPS:
                pieces.append(_BIG_OPS[command])
                index = next_index
                continue

            if command in _FUNC_NAMES:
                pieces.append(command)
                index = next_index
                continue

            if command in _NAMED_SYMBOLS:
                pieces.append(_NAMED_SYMBOLS[command])
                index = next_index
                continue

            if token in _DELIMITER_COMMANDS:
                pieces.append(_DELIMITER_COMMANDS[token])
                index = next_index
                continue

            # 未知命令保守处理：去掉反斜杠，保留命令名，避免直接丢失信息。
            pieces.append(command or token.lstrip("\\"))
            index = next_index
            continue

        if char in "^_":
            argument_raw, index = _consume_argument(tex, index + 1)
            pieces.append(_format_script(_convert_inner(argument_raw), superscript=(char == "^")))
            continue

        if char == "{":
            group_raw, index = _consume_group(tex, index, "{", "}")
            pieces.append(_convert_inner(group_raw))
            continue

        if char == "}":
            index += 1
            continue

        pieces.append(char)
        index += 1

    return _normalize_result("".join(pieces))


def latex_to_unicode(text: str) -> str:
    """将文本中的 LaTeX 数学公式（$...$, $$...$$）转为 Unicode 可读形式。

    非数学部分保持不变。
    """

    def _replace_match(match: Match[str]) -> str:
        inner = match.group(1) or match.group(2)
        return _convert_inner(inner)

    return _LATEX_BLOCK_RE.sub(_replace_match, text)
