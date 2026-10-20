"""408 图中的位宽比例、时间区间、树方向与真实渲染接入。"""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("numpy")

from helpers import run_script
from cs_figure_style import field_strip, timeline, binary_tree
from math_figure_style import configure
from test_create_figure import make_kind, QID
from test_create_wrong_card import create_card


def test_field_strip_uses_actual_bit_widths_and_total():
    configure()
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    strips = field_strip(ax, [("Tag", 20), ("Index", 7), ("Offset", 5)], 32)
    assert [patch.get_width() for patch in strips] == [20, 7, 5]
    assert [patch.get_x() for patch in strips] == [0, 20, 27]
    assert strips[-1].get_x() + strips[-1].get_width() == 32
    plt.close(fig)


@pytest.mark.parametrize("fields,total", [([("Tag", 10), ("Index", 2)], 16), ([("Tag", 0)], 0), ([("Tag", 1.5)], 1.5)])
def test_field_strip_rejects_invalid_widths(fields, total):
    configure()
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    with pytest.raises(ValueError):
        field_strip(ax, fields, total)
    plt.close(fig)


def test_timeline_preserves_durations_and_rejects_cpu_overlap():
    configure()
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    patches = timeline(ax, [("P1", 0, 3), ("P2", 3, 5), ("P3", 5, 9)])
    assert [(patch.get_x(), patch.get_width()) for patch in patches] == [(0, 3), (3, 2), (5, 4)]
    with pytest.raises(ValueError, match="不能重叠"):
        timeline(ax, [("P1", 0, 3), ("P2", 2, 5)])
    with pytest.raises(ValueError, match="正时长"):
        timeline(ax, [("P1", 3, 3)])
    plt.close(fig)


def test_rotation_preserves_inorder_positions_and_child_directions():
    configure()
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2)
    before = {30: (20, None), 20: (10, None)}
    after = {20: (10, 30)}
    first = binary_tree(axes[0], before, 30)
    second = binary_tree(axes[1], after, 20)
    assert set(first) == set(second) == {10, 20, 30}
    assert {node: position[0] for node, position in first.items()} == {node: position[0] for node, position in second.items()}
    for children, positions in ((before, first), (after, second)):
        for parent, (left, right) in children.items():
            if left is not None:
                assert positions[left][0] < positions[parent][0]
            if right is not None:
                assert positions[right][0] > positions[parent][0]
    with pytest.raises(ValueError, match="环或共享"):
        binary_tree(axes[0], {1: (2, None), 2: (1, None)}, 1)
    plt.close(fig)


@pytest.mark.parametrize("example", ["tree", "linked_list", "cache", "pipeline", "scheduling", "network"])
def test_408_templates_render_as_svg_and_can_enter_card(vault_root, example):
    template = Path(__file__).resolve().parent.parent / "templates" / "408_figure_examples.py"
    source = template.read_text().replace('EXAMPLE = "cache"', f'EXAMPLE = "{example}"')
    rc, payload = make_kind(vault_root, "python", source, slug=example, caption="图1：示例机制图", extra=["--width", "640"])
    assert rc == 0, payload
    assert not payload["warnings"], payload["warnings"]
    root = ET.fromstring(Path(payload["path"]).read_text())
    assert root.get("viewBox") and len(list(root.iter())) > 10
    assert Path(payload["preview_path"]).is_file()
    rc, out, err = create_card(vault_root, "408", QID, "Cache 映射", ["--figure", payload["figure_arg"]])
    assert rc == 0, out + err
    text = Path(json.loads(out)["path"]).read_text()
    assert payload["embed"] in text
    assert text.index("### 破题密码") < text.index("### 图示") < text.index("### 暴力扫雷")
    # 图放详解区，CLI 纯文本预览不应泄漏嵌入语法。
    from figure_ops import replace_figure_embeds_for_cli
    assert "![[" not in replace_figure_embeds_for_cli(payload["embed"])
