#!/usr/bin/env python3
"""将 LaTeX 数学公式转为 Unicode 可读文本，供 CLI 环境下阅读。

仅做"尽力转写"，覆盖考研数学常见符号；
极端嵌套公式可能仍不完美，但比原始 LaTeX 可读性好得多。
"""
import re

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
_SUP = str.maketrans("0123456789+-=()nixy", "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079\u207a\u207b\u207c\u207d\u207e\u207f\u2071\u02e3\u02b8")
_SUB = str.maketrans("0123456789+-=()aeioruvx", "\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089\u208a\u208b\u208c\u208d\u208e\u2090\u2091\u1d62\u2092\u1d63\u1d64\u1d65\u2093")

# ---------- 简单符号替换 ----------
_SYMBOLS = {
    r"\cdot": "\u00b7",
    r"\times": "\u00d7",
    r"\div": "\u00f7",
    r"\pm": "\u00b1",
    r"\mp": "\u2213",
    r"\leq": "\u2264", r"\le": "\u2264",
    r"\geq": "\u2265", r"\ge": "\u2265",
    r"\neq": "\u2260", r"\ne": "\u2260",
    r"\approx": "\u2248",
    r"\equiv": "\u2261",
    r"\sim": "\u223c",
    r"\propto": "\u221d",
    r"\infty": "\u221e",
    r"\partial": "\u2202",
    r"\nabla": "\u2207",
    r"\forall": "\u2200",
    r"\exists": "\u2203",
    r"\in": "\u2208",
    r"\notin": "\u2209",
    r"\subset": "\u2282",
    r"\supset": "\u2283",
    r"\cup": "\u222a",
    r"\cap": "\u2229",
    r"\emptyset": "\u2205",
    r"\to": "\u2192", r"\rightarrow": "\u2192",
    r"\leftarrow": "\u2190",
    r"\Rightarrow": "\u21d2", r"\implies": "\u21d2",
    r"\Leftarrow": "\u21d0",
    r"\Leftrightarrow": "\u21d4", r"\iff": "\u21d4",
    r"\ldots": "\u2026", r"\cdots": "\u22ef", r"\dots": "\u2026",
    r"\prime": "\u2032",
    r"\quad": " ", r"\qquad": "  ",
    r"\,": " ", r"\;": " ", r"\!": "",
    r"\%": "%",
}

# ---------- 大运算符 ----------
_BIG_OPS = {
    "sum": "\u2211", "prod": "\u220f", "int": "\u222b",
    "iint": "\u222c", "iiint": "\u222d", "oint": "\u222e",
    "bigcup": "\u22c3", "bigcap": "\u22c2",
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

# ---------- 正则 ----------
_LATEX_BLOCK_RE = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$", re.S)


def _strip_braces(s: str) -> str:
    """去掉最外层花括号（如果有的话）。"""
    s = s.strip()
    if s.startswith("{") and s.endswith("}"):
        return s[1:-1]
    return s


def _find_brace_group(tex: str, start: int) -> str:
    """从 start 位置开始匹配 {...}，返回花括号内的内容。"""
    if start >= len(tex) or tex[start] != "{":
        # 没有花括号，取单个字符
        if start < len(tex):
            return tex[start]
        return ""
    depth = 0
    for i in range(start, len(tex)):
        if tex[i] == "{":
            depth += 1
        elif tex[i] == "}":
            depth -= 1
            if depth == 0:
                return tex[start + 1:i]
    return tex[start + 1:]


def _to_superscript(text: str) -> str:
    return text.translate(_SUP)


def _to_subscript(text: str) -> str:
    return text.translate(_SUB)


def _convert_inner(tex: str) -> str:  # noqa: C901
    """将单个 LaTeX 数学表达式（不含 $ 定界符）转为 Unicode。"""
    out = tex

    # 1) \text{...} / \mathrm{...} / \textbf{...} → 内容原样保留
    out = re.sub(r"\\(?:text|mathrm|textbf|mathbf|mathit|operatorname)\{([^}]*)\}", r"\1", out)

    # 2) 希腊字母
    for cmd, char in _GREEK.items():
        out = re.sub(r"\\%s(?![a-zA-Z])" % cmd, char, out)

    # 3) 大运算符（在简单符号替换之前，避免 \in 吃掉 \int）
    for cmd, char in _BIG_OPS.items():
        out = re.sub(r"\\%s(?![a-zA-Z])" % cmd, char, out)

    # 4) \lim 和函数名  \sin → sin
    out = re.sub(r"\\lim(?![a-zA-Z])", "lim", out)
    for fn in _FUNC_NAMES:
        out = re.sub(r"\\%s(?![a-zA-Z])" % fn, fn, out)

    # 5) 简单符号（\in 等用 regex 避免误匹配 \int 等）
    for cmd, char in _SYMBOLS.items():
        if cmd in (r"\in", r"\notin"):
            out = re.sub(re.escape(cmd) + r"(?![a-zA-Z])", char, out)
        else:
            out = out.replace(cmd, char)

    # 6) \sqrt[n]{x} → ⁿ√(x)  ;  \sqrt{x} → √(x)
    # 带可选参数
    out = re.sub(
        r"\\sqrt\[([^\]]*)\]\{([^}]*)\}",
        lambda m: _to_superscript(_convert_inner(m.group(1))) + "\u221a(" + _convert_inner(m.group(2)) + ")",
        out,
    )
    # 不带可选参数
    out = re.sub(
        r"\\sqrt\{([^}]*)\}",
        lambda m: "\u221a(" + _convert_inner(m.group(1)) + ")",
        out,
    )

    # 7) \frac{a}{b} → (a)/(b)  — 简单内容省略括号
    def _repl_frac(m):
        num = _convert_inner(m.group(1))
        den = _convert_inner(m.group(2))
        if len(num) <= 2 and num.isalnum():
            num_part = num
        else:
            num_part = "(" + num + ")"
        if len(den) <= 2 and den.isalnum():
            den_part = den
        else:
            den_part = "(" + den + ")"
        return num_part + "/" + den_part
    out = re.sub(r"\\(?:frac|dfrac|tfrac)\{([^}]*)\}\{([^}]*)\}", _repl_frac, out)

    # 8) \left( \right)  → ( )
    out = re.sub(r"\\left\s*([(\[{|.])", r"\1", out)
    out = re.sub(r"\\right\s*([)\]}|.])", r"\1", out)
    out = out.replace(r"\left", "").replace(r"\right", "")

    # 9) \overline{x} → x̄
    out = re.sub(r"\\overline\{([^}])\}", lambda m: m.group(1) + "\u0304", out)
    out = re.sub(r"\\overline\{([^}]+)\}", lambda m: "(" + m.group(1) + ")\u0304", out)
    # \hat{x} → x̂
    out = re.sub(r"\\hat\{([^}])\}", lambda m: m.group(1) + "\u0302", out)
    # \vec{x} → x⃗
    out = re.sub(r"\\vec\{([^}])\}", lambda m: m.group(1) + "\u20d7", out)

    # 10) 上标 ^{...} → 上标字符
    def _repl_sup(m):
        content = _convert_inner(m.group(1))
        converted = _to_superscript(content)
        if converted == content:
            # 无法转为上标字符，用 ^ 保留
            return "^(" + content + ")" if len(content) > 1 else "^" + content
        return converted
    out = re.sub(r"\^\{([^}]*)\}", _repl_sup, out)
    # 单字符上标 ^x
    def _repl_sup_single(m):
        ch = m.group(1)
        converted = _to_superscript(ch)
        return converted if converted != ch else "^" + ch
    out = re.sub(r"\^([A-Za-z0-9])", _repl_sup_single, out)

    # 11) 下标 _{...} → 下标字符
    def _repl_sub(m):
        content = _convert_inner(m.group(1))
        converted = _to_subscript(content)
        if converted == content:
            return "_(" + content + ")" if len(content) > 1 else "_" + content
        return converted
    out = re.sub(r"_\{([^}]*)\}", _repl_sub, out)
    # 单字符下标 _x
    def _repl_sub_single(m):
        ch = m.group(1)
        converted = _to_subscript(ch)
        return converted if converted != ch else "_" + ch
    out = re.sub(r"_([A-Za-z0-9])", _repl_sub_single, out)

    # 13) 清理残余花括号和多余空格
    out = out.replace("{", "").replace("}", "")
    out = re.sub(r"  +", " ", out)

    return out.strip()


def latex_to_unicode(text: str) -> str:
    """将文本中的 LaTeX 数学公式（$...$, $$...$$）转为 Unicode 可读形式。

    非数学部分保持不变。
    """
    def _replace_match(m):
        # group(1) 是 $$...$$ 的内容，group(2) 是 $...$ 的内容
        inner = m.group(1) or m.group(2)
        return _convert_inner(inner)
    return _LATEX_BLOCK_RE.sub(_replace_match, text)
