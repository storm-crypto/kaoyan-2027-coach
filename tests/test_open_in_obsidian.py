"""test open_in_obsidian.py

全部用 `--print-only`，避免测试真的把 Obsidian 弹到前台。
"""
import json
from urllib.parse import quote

from helpers import run_script


def _run(args):
    rc, out, err = run_script("open_in_obsidian.py", args + ["--print-only"])
    return rc, out, err


def test_vault_root_detected_above_obsidian_root(vault_root, sample_card):
    """vault 根可能在 OBSIDIAN_ROOT 之上——真实库就是
    `<vault>/10_Projects/Kaoyan_2027_Prep/错题本/`，不能拿 OBSIDIAN_ROOT 当 vault 根。"""
    (vault_root / ".obsidian").mkdir()
    nested_root = vault_root / "10_Projects" / "Kaoyan_2027_Prep"
    nested_root.mkdir(parents=True)
    card = nested_root / "错题本" / "数学一" / sample_card.name
    card.parent.mkdir(parents=True)
    card.write_text(sample_card.read_text(encoding="utf-8"), encoding="utf-8")

    rc, out, _ = _run([str(nested_root), "--path", str(card)])

    assert rc == 0
    data = json.loads(out)
    assert data["vault_root"] == str(vault_root)
    assert data["vault"] == vault_root.name
    assert data["opened"] is False
    # file 参数按链接目标解析，.md 要去掉；中文和斜杠都要百分号编码
    expected = quote(f"10_Projects/Kaoyan_2027_Prep/错题本/数学一/{card.stem}", safe="")
    assert data["uri"] == f"obsidian://open?vault={quote(vault_root.name, safe='')}&file={expected}"
    assert "%E9%94%99%E9%A2%98%E6%9C%AC" in data["uri"]  # “错题本”确实被编码了
    assert data["uri_by_path"] == f"obsidian://open?path={quote(str(card), safe='')}"


def test_falls_back_to_obsidian_root_when_no_dot_obsidian(vault_root, sample_card):
    rc, out, _ = _run([str(vault_root), "--path", str(sample_card)])

    assert rc == 0
    data = json.loads(out)
    assert data["vault_root"] == str(vault_root)
    assert any(".obsidian" in w for w in data["warnings"])


def test_relative_path_resolves_against_obsidian_root(vault_root, sample_card):
    relative = sample_card.relative_to(vault_root)

    rc, out, _ = _run([str(vault_root), "--path", str(relative)])

    assert rc == 0
    assert json.loads(out)["path"] == str(sample_card)


def test_question_id_lookup(vault_root, sample_card):
    rc, out, _ = _run([str(vault_root), "--question-id", "qid-f728c5b18974"])

    assert rc == 0
    assert json.loads(out)["path"] == str(sample_card)


def test_question_id_not_found(vault_root, sample_card):
    rc, out, _ = _run([str(vault_root), "--question-id", "qid-doesnotexist"])

    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True
    assert "qid-doesnotexist" in data["message"]


def test_missing_file(vault_root):
    rc, out, _ = _run([str(vault_root), "--path", str(vault_root / "错题本" / "不存在.md")])

    assert rc == 1
    assert json.loads(out)["error"] is True


def test_file_outside_vault_is_rejected(vault_root, tmp_path):
    outside = tmp_path.parent / "外部笔记.md"
    outside.write_text("# 不在库里", encoding="utf-8")

    rc, out, _ = _run([str(vault_root), "--path", str(outside)])

    assert rc == 1
    data = json.loads(out)
    assert data["error"] is True
    assert "不在 vault 内" in data["message"]


def test_path_and_question_id_are_mutually_exclusive(vault_root, sample_card):
    rc, _, err = run_script("open_in_obsidian.py", [
        str(vault_root), "--path", str(sample_card), "--question-id", "qid-f728c5b18974", "--print-only"
    ])

    assert rc == 2
    assert "not allowed with" in err
