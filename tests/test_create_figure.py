"""test create_figure.py 与错题卡配图落盘。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from helpers import run_script

QID = "qid-a1b2c3d4e5f6"

VALID_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 320" role="img" aria-label="积分区域">
  <style>
    :root{--ink:#1f2933;--bg:#fdfdfb;--accent:#2f6f9f}
    @media (prefers-color-scheme: dark){:root{--ink:#e6e8eb;--bg:#1e1f22;--accent:#7fb3d5}}
    text{font-family:Arial,sans-serif;font-size:14px}
    .bg{fill:var(--bg)} .ink{fill:var(--ink)} .axis{stroke:var(--ink)}
  </style>
  <rect class="bg" x="0" y="0" width="480" height="320" fill="#fdfdfb"/>
  <path class="axis" d="M60 270 H440" stroke="#1f2933" stroke-width="1.5" fill="none"/>
  <text class="ink" x="200" y="240" fill="#1f2933">D</text>
</svg>"""


def make_figure(vault_root, svg=VALID_SVG, slug="积分区域", caption="图1：原积分区域 D", extra=None):
    """跑 create_figure.py，返回 (rc, payload)。payload 是解析后的 JSON。"""
    args = [
        str(vault_root),
        "--question-id", QID,
        "--slug", slug,
        "--caption", caption,
    ] + (extra or [])
    rc, out, err = run_script_with_stdin("create_figure.py", args, svg)
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        payload = {"raw_stdout": out, "stderr": err}
    return rc, payload


def run_script_with_stdin(script_name, args, stdin_text):
    import os
    import subprocess
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    result = subprocess.run(
        ["python3", str(scripts_dir / script_name)] + args,
        input=stdin_text,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        cwd=str(scripts_dir),
    )
    return result.returncode, result.stdout, result.stderr


# ---------- 落盘 ----------

def test_valid_svg_lands_under_figure_dir(vault_root):
    rc, payload = make_figure(vault_root)
    assert rc == 0, payload
    expected = vault_root / "错题本" / "_附图" / QID / f"{QID}-01-积分区域.svg"
    assert expected.is_file()
    assert payload["relative_path"] == f"错题本/_附图/{QID}/{QID}-01-积分区域.svg"
    assert payload["embed"] == f"![[错题本/_附图/{QID}/{QID}-01-积分区域.svg|480]]"
    assert payload["figure_arg"] == f"错题本/_附图/{QID}/{QID}-01-积分区域.svg|图1：原积分区域 D"


def test_index_auto_increments_for_new_slug(vault_root):
    make_figure(vault_root, slug="积分区域")
    rc, payload = make_figure(vault_root, slug="换序后条带", caption="图2：换序后")
    assert rc == 0, payload
    assert payload["index"] == 2


def test_same_slug_overwrites_in_place(vault_root):
    make_figure(vault_root, slug="积分区域")
    rc, payload = make_figure(vault_root, slug="积分区域")
    assert rc == 0, payload
    assert payload["index"] == 1
    files = list((vault_root / "错题本" / "_附图" / QID).glob("*.svg"))
    assert len(files) == 1


def test_dry_run_does_not_write(vault_root):
    rc, payload = make_figure(vault_root, extra=["--dry-run"])
    assert rc == 0, payload
    assert payload["dry_run"] is True
    assert not (vault_root / "错题本" / "_附图" / QID).exists()


def test_latex_in_text_is_converted_to_unicode(vault_root):
    svg = VALID_SVG.replace(">D</text>", ">$y = x^2$</text>")
    rc, payload = make_figure(vault_root, svg=svg)
    assert rc == 0, payload
    content = Path(payload["path"]).read_text(encoding="utf-8")
    assert "y = x²" in content
    assert "$" not in content
    assert any("Unicode" in w for w in payload["warnings"])


def test_custom_width_flows_into_embed_and_figure_arg(vault_root):
    rc, payload = make_figure(vault_root, extra=["--width", "640"])
    assert rc == 0, payload
    assert payload["embed"].endswith("|640]]")
    assert payload["figure_arg"].endswith("|640")


# ---------- 拒绝 ----------

def assert_rejected(vault_root, svg, keyword, extra=None):
    rc, payload = make_figure(vault_root, svg=svg, extra=extra)
    assert rc == 1, payload
    assert payload.get("error") is True
    assert keyword in payload["message"], payload["message"]
    assert not (vault_root / "错题本" / "_附图" / QID).exists()


def test_rejects_non_xml(vault_root):
    assert_rejected(vault_root, "<svg viewBox='0 0 1 1'><rect>", "合法 XML")


def test_rejects_non_svg_root(vault_root):
    assert_rejected(vault_root, "<html><body/></html>", "根元素必须是 <svg>")


def test_rejects_missing_viewbox(vault_root):
    svg = VALID_SVG.replace(' viewBox="0 0 480 320"', "")
    assert_rejected(vault_root, svg, "viewBox")


def test_rejects_script_element(vault_root):
    svg = VALID_SVG.replace("<rect", "<script>alert(1)</script><rect", 1)
    assert_rejected(vault_root, svg, "<script>")


def test_rejects_foreign_object(vault_root):
    svg = VALID_SVG.replace("<rect", "<foreignObject width='10' height='10'/><rect", 1)
    assert_rejected(vault_root, svg, "<foreignObject>")


def test_rejects_event_attribute(vault_root):
    svg = VALID_SVG.replace('role="img"', 'role="img" onload="boom()"', 1)
    assert_rejected(vault_root, svg, "事件属性")


def test_rejects_external_url(vault_root):
    svg = VALID_SVG.replace(">D</text>", ">https://example.com</text>")
    assert_rejected(vault_root, svg, "外链")


def test_rejects_raster_image_element(vault_root):
    svg = VALID_SVG.replace("<rect", "<image width='10' height='10'/><rect", 1)
    assert_rejected(vault_root, svg, "<image>")


def test_rejects_tiny_font_size(vault_root):
    svg = VALID_SVG.replace("font-size:14px", "font-size:10px")
    assert_rejected(vault_root, svg, "字号过小")


def test_rejects_font_family_without_generic_fallback(vault_root):
    svg = VALID_SVG.replace("font-family:Arial,sans-serif", "font-family:LatinModernMath")
    assert_rejected(vault_root, svg, "通用兜底字体")


def test_rejects_missing_dark_mode_adaptation(vault_root):
    svg = VALID_SVG.replace("@media (prefers-color-scheme: dark){:root{--ink:#e6e8eb;--bg:#1e1f22;--accent:#7fb3d5}}", "")
    assert_rejected(vault_root, svg, "深色模式适配")


def test_allow_fixed_theme_bypasses_dark_mode_check(vault_root):
    svg = VALID_SVG.replace("@media (prefers-color-scheme: dark){:root{--ink:#e6e8eb;--bg:#1e1f22;--accent:#7fb3d5}}", "")
    rc, payload = make_figure(vault_root, svg=svg, extra=["--allow-fixed-theme"])
    assert rc == 0, payload


def test_rejects_leftover_latex_commands(vault_root):
    svg = VALID_SVG.replace(">D</text>", ">\\iiint_D</text>")
    assert_rejected(vault_root, svg, "未转写的 LaTeX")


def test_rejects_oversized_svg(vault_root):
    filler = "<path d='M0 0 H1' stroke='#1f2933'/>" * 900
    svg = VALID_SVG.replace("<rect", filler + "<rect", 1)
    assert_rejected(vault_root, svg, "超过上限")


def test_rejects_bad_question_id(vault_root):
    rc, out, _ = run_script_with_stdin(
        "create_figure.py",
        [str(vault_root), "--question-id", "qid-zzz", "--slug", "x", "--caption", "图1：x"],
        VALID_SVG,
    )
    assert rc == 1
    assert "question_id 格式非法" in json.loads(out)["message"]


def test_rejects_caption_with_separator(vault_root):
    rc, payload = make_figure(vault_root, caption="图1：含|分隔符")
    assert rc == 1, payload
    assert "`|`" in payload["message"]


def test_warns_when_caption_is_not_numbered(vault_root):
    rc, payload = make_figure(vault_root, caption="原积分区域 D")
    assert rc == 0, payload
    assert any("图1：" in w for w in payload["warnings"])


# ---------- 上色兜底（不支持 CSS 变量的渲染器里会整张变黑块）----------

def test_rejects_var_in_paint_attribute(vault_root):
    """fill="var(--x)" 会让整个属性失效、回落成黑色，必须硬拦。"""
    svg = VALID_SVG.replace('<rect class="bg" x="0" y="0" width="480" height="320" fill="#fdfdfb"/>',
                            '<rect class="bg" x="0" y="0" width="480" height="320" fill="var(--bg)"/>')
    assert_rejected(vault_root, svg, "不安全")


def test_rejects_var_in_stroke_attribute(vault_root):
    svg = VALID_SVG.replace('stroke="#1f2933"', 'stroke="var(--ink)"')
    assert_rejected(vault_root, svg, "不安全")


def test_warns_when_element_has_no_literal_paint_fallback(vault_root):
    """只靠 CSS 类上色、元素上没有字面兜底色 → 告警但放行。"""
    svg = VALID_SVG.replace(' fill="#1f2933">D</text>', '>D</text>')
    rc, payload = make_figure(vault_root, svg=svg)
    assert rc == 0, payload
    assert any("没有字面兜底色" in w for w in payload["warnings"]), payload["warnings"]


def test_no_paint_warning_for_well_formed_svg(vault_root):
    rc, payload = make_figure(vault_root)
    assert rc == 0, payload
    assert not any("兜底色" in w for w in payload["warnings"]), payload["warnings"]
