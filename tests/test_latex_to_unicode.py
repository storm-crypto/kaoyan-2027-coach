"""test latex_to_unicode.py — LaTeX → Unicode 转写测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from latex_to_unicode import latex_to_unicode, _convert_inner


# ---------- 基础符号 ----------

def test_simple_operators():
    assert "\u2264" in latex_to_unicode("$a \\leq b$")  # ≤
    assert "\u2265" in latex_to_unicode("$a \\geq b$")  # ≥
    assert "\u2260" in latex_to_unicode("$a \\neq b$")  # ≠
    assert "\u221e" in latex_to_unicode("$\\infty$")     # ∞
    assert "\u00d7" in latex_to_unicode("$a \\times b$") # ×
    assert "\u00b7" in latex_to_unicode("$a \\cdot b$")  # ·


def test_greek_letters():
    assert "\u03b1" in latex_to_unicode("$\\alpha$")
    assert "\u03b2" in latex_to_unicode("$\\beta$")
    assert "\u03c0" in latex_to_unicode("$\\pi$")
    assert "\u03a3" in latex_to_unicode("$\\Sigma$")


def test_arrows_and_logic():
    assert "\u2192" in latex_to_unicode("$x \\to y$")
    assert "\u21d2" in latex_to_unicode("$A \\Rightarrow B$")


# ---------- 上标 / 下标 ----------

def test_superscript_single():
    result = latex_to_unicode("$x^2$")
    assert "\u00b2" in result  # ²


def test_superscript_braced():
    result = latex_to_unicode("$x^{n+1}$")
    assert "\u207f" in result  # ⁿ
    assert "\u207a" in result  # ⁺
    assert "\u00b9" in result  # ¹


def test_subscript_single():
    result = latex_to_unicode("$x_1$")
    assert "\u2081" in result  # ₁


def test_subscript_braced():
    result = latex_to_unicode("$a_{ij}$")
    assert "\u1d62" in result  # ᵢ


# ---------- 分式 ----------

def test_frac_simple():
    result = latex_to_unicode("$\\frac{1}{2}$")
    assert result == "1/2"


def test_frac_complex():
    result = latex_to_unicode("$\\frac{x+1}{x-1}$")
    assert "(x+1)/(x-1)" in result


def test_dfrac():
    result = latex_to_unicode("$\\dfrac{a}{b}$")
    assert "a/b" in result


# ---------- 根号 ----------

def test_sqrt():
    result = latex_to_unicode("$\\sqrt{x}$")
    assert "\u221a" in result  # √
    assert "x" in result


def test_sqrt_nth():
    result = latex_to_unicode("$\\sqrt[3]{x}$")
    assert "\u221a" in result
    assert "\u00b3" in result  # ³


# ---------- 大运算符 ----------

def test_sum():
    result = latex_to_unicode("$\\sum_{i=1}^{n} x_i$")
    assert "\u2211" in result  # Σ


def test_integral():
    result = latex_to_unicode("$\\int_{0}^{1} f(x) dx$")
    assert "\u222b" in result  # ∫


def test_lim():
    result = latex_to_unicode("$\\lim_{n \\to \\infty} a_n$")
    assert "lim" in result
    assert "\u221e" in result


# ---------- 函数名 ----------

def test_trig_functions():
    result = latex_to_unicode("$\\sin x + \\cos x$")
    assert "sin" in result
    assert "cos" in result


def test_log_ln():
    assert "ln" in latex_to_unicode("$\\ln x$")
    assert "log" in latex_to_unicode("$\\log_2 x$")


# ---------- \text / \mathrm ----------

def test_text():
    result = latex_to_unicode("$\\text{if } x > 0$")
    assert "if" in result
    assert "$" not in result


def test_mathrm():
    result = latex_to_unicode("$\\mathrm{d}x$")
    assert "dx" in result


# ---------- 括号 ----------

def test_left_right():
    result = latex_to_unicode("$\\left( \\frac{a}{b} \\right)$")
    assert "(" in result
    assert ")" in result
    assert "$" not in result


# ---------- 装饰 ----------

def test_overline():
    result = latex_to_unicode("$\\overline{x}$")
    assert "x" in result
    assert "\u0304" in result  # combining overline


def test_hat():
    result = latex_to_unicode("$\\hat{x}$")
    assert "\u0302" in result


# ---------- 混合文本 ----------

def test_mixed_text_and_math():
    text = "若 $f''(x) > 0$，则函数 $f(x)$ 在区间上为凸。"
    result = latex_to_unicode(text)
    assert "若" in result
    assert "则函数" in result
    assert "在区间上为凸。" in result
    assert "$" not in result


def test_display_math():
    text = "求 $$\\int_0^1 x^2 dx$$ 的值"
    result = latex_to_unicode(text)
    assert "\u222b" in result
    assert "求" in result
    assert "的值" in result
    assert "$$" not in result


def test_no_latex_passthrough():
    text = "这是一个没有公式的普通句子。"
    assert latex_to_unicode(text) == text


def test_empty_string():
    assert latex_to_unicode("") == ""


# ---------- 考研典型公式 ----------

def test_kaoyan_typical_formula():
    """考研数学常见的二阶导+凹凸性判定。"""
    text = "若 $f''(x) > 0$，判断函数图像的凹凸性。"
    result = latex_to_unicode(text)
    assert "$" not in result
    assert "f" in result
    assert ">" in result
    assert "0" in result


def test_kaoyan_fraction_inequality():
    """典型分式不等式。"""
    text = "$f^2\\left(\\frac{x_1+x_2}{2}\\right) < \\frac{f^2(x_1)+f^2(x_2)}{2}$"
    result = latex_to_unicode(text)
    assert "$" not in result
    assert "/" in result  # fraction converted
    assert "<" in result
    assert "\\right" not in result
    assert "\u2264ft" not in result


def test_partial_derivative():
    text = "$\\frac{\\partial f}{\\partial x}$"
    result = latex_to_unicode(text)
    assert "\u2202" in result  # ∂
    assert "/" in result


def test_multiple_formulas_in_line():
    text = "已知 $a > 0$，$b < 0$，求 $a + b$ 的范围。"
    result = latex_to_unicode(text)
    assert "$" not in result
    assert "已知" in result
    assert "求" in result


def test_nested_fraction_regression():
    result = latex_to_unicode("$\\frac{\\frac{a}{b}}{c}$")
    assert result == "(a/b)/c"


def test_nested_sqrt_fraction_regression():
    result = latex_to_unicode("$\\sqrt{1+\\frac{1}{x}}$")
    assert result == "\u221a(1+1/x)"


def test_left_right_regression():
    result = latex_to_unicode("$\\left(\\frac{x+1}{x-1}\\right)^2$")
    assert result == "((x+1)/(x-1))\u00b2"


def test_fraction_with_subscripts_regression():
    result = latex_to_unicode("$\\frac{a_{n+1}}{b_n}$")
    assert result == "a\u2099\u208a\u2081/b\u2099"
