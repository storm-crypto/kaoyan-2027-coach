"""Python 配图真实渲染、失败保全与题卡接入。"""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("numpy")

from helpers import run_script
from test_create_figure import make_kind, make_figure, QID
from test_create_wrong_card import create_card

SOURCE = '''import numpy as np
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(7, 4), layout="constrained")
x = np.linspace(0, 1, 101)
ax.plot(x, x**2)
ax.set_title(r"积分区域 $y=x^2$")
ax.fill_between(x, x**2, x, alpha=0.2)
'''


def test_python_renders_portable_svg_preview_and_source_and_embeds(vault_root):
    from PIL import Image
    rc, payload = make_kind(vault_root, "python", SOURCE, slug="读限", caption="图1：区域边界", extra=["--width", "640"])
    assert rc == 0, payload
    svg = Path(payload["path"])
    root = ET.fromstring(svg.read_text())
    assert root.get("viewBox")
    tags = {element.tag.rsplit("}", 1)[-1] for element in root.iter()}
    assert "path" in tags and "text" not in tags  # 字形已烘焙，不依赖阅读端字体
    assert "metadata" not in tags
    assert Path(payload["source_path"]).read_text().strip() == SOURCE.strip()
    with Image.open(payload["preview_path"]) as image:
        assert image.width > 1000 and image.height > 500
        assert len(image.convert("RGB").getcolors(image.width * image.height)) > 100
    assert payload["rendered"] is True
    assert payload["figure_arg"].endswith("|640")
    rc, out, err = create_card(vault_root, "数学一", QID, "数列极限", ["--figure", payload["figure_arg"]])
    assert rc == 0, out + err
    card = Path(json.loads(out)["path"])
    text = card.read_text()
    assert payload["embed"] in text
    assert text.index("### 第一步怎么想到") < text.index("### 图示") < text.index("### 规范解法")
    # 复习补图沿用同一个入口；不能覆盖原图示。
    rc, second = make_kind(vault_root, "python", SOURCE, slug="横切", caption="图2：横切边界")
    assert rc == 0, second
    rc, out, err = run_script("update_card.py", [str(card), "--status", "半会", "--figure", second["figure_arg"]])
    assert rc == 0, out + err
    updated = card.read_text()
    assert payload["embed"] in updated and second["embed"] in updated


def test_python_dry_run_does_not_execute_source_or_write(vault_root, tmp_path):
    marker = tmp_path / "must-not-exist"
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    rc, payload = make_kind(vault_root, "python", source, extra=["--dry-run"])
    assert rc == 0, payload
    assert payload["rendered"] is False
    assert not marker.exists()
    assert not Path(payload["path"]).parent.exists()
    assert any("只检查 Python 语法" in warning for warning in payload["warnings"])


@pytest.mark.parametrize("source,keyword", [
    ("fig = (", "语法错误"),
    ("raise ValueError('bad-math')", "bad-math"),
    ("import matplotlib.pyplot as plt\nplt.subplots()", "赋给 fig"),
    ("import matplotlib.pyplot as plt\nfig = plt.figure()", "空白图"),
])
def test_failed_render_leaves_no_vault_artifacts(vault_root, source, keyword):
    rc, payload = make_kind(vault_root, "python", source)
    assert rc == 1 and payload["error"] is True, payload
    assert keyword in payload["message"]
    assert not (vault_root / "错题本" / "_附图" / QID).exists()


def test_failed_redraw_preserves_all_previous_artifacts(vault_root):
    rc, original = make_kind(vault_root, "python", SOURCE)
    assert rc == 0, original
    files = [Path(original[key]) for key in ("path", "source_path", "preview_path")]
    before = [path.read_bytes() for path in files]
    rc, payload = make_kind(vault_root, "python", "raise ValueError('redraw-failed')")
    assert rc == 1, payload
    assert before == [path.read_bytes() for path in files]


def test_python_figures_share_numbering_with_legacy_sources(vault_root):
    assert make_figure(vault_root, slug="旧区域")[0] == 0
    rc, new = make_kind(vault_root, "python", SOURCE, slug="新区域")
    assert rc == 0, new
    assert new["index"] == 2
    rc, redraw = make_kind(vault_root, "python", SOURCE, slug="新区域")
    assert rc == 0, redraw
    assert redraw["path"] == new["path"]
    rc, third = make_figure(vault_root, slug="第三步")
    assert rc == 0 and third["index"] == 3, third


def test_python_can_render_three_dimensional_figure(vault_root):
    source = '''import numpy as np
import matplotlib.pyplot as plt
fig = plt.figure(figsize=(7, 5), layout="constrained")
ax = fig.add_subplot(111, projection="3d")
u = np.linspace(-1, 1, 12)
X, Y = np.meshgrid(u, u)
ax.plot_surface(X, Y, X**2 + Y**2, alpha=0.4)
ax.set(xlabel="$x$", ylabel="$y$", zlabel="$z$")
'''
    rc, payload = make_kind(vault_root, "python", source)
    assert rc == 0, payload
    assert Path(payload["preview_path"]).stat().st_size > 1000
