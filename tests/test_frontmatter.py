"""test frontmatter.py"""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from frontmatter import parse_frontmatter, parse_frontmatter_field, serialize_frontmatter


def test_parse_frontmatter_supports_crlf():
    text = (
        "---\r\n"
        "source: 900题\r\n"
        "question_id: qid-aabbccddeeff\r\n"
        "error_tags: [极坐标, \"item, with comma\"]\r\n"
        "---\r\n"
        "\r\n"
        "正文内容\r\n"
    )

    fm, body, key_order = parse_frontmatter(text)

    assert fm["source"] == "900题"
    assert fm["question_id"] == "qid-aabbccddeeff"
    assert fm["error_tags"] == ["极坐标", "item, with comma"]
    assert key_order == ["source", "question_id", "error_tags"]
    assert body.startswith("\r\n")
    assert "正文内容" in body


def test_parse_frontmatter_field_supports_crlf():
    text = "---\r\nsource: 王道\r\nquestion_id: qid-112233445566\r\n---\r\n"
    assert parse_frontmatter_field(text, "source") == "王道"
    assert parse_frontmatter_field(text, "question_id") == "qid-112233445566"


def test_serialize_frontmatter_roundtrip():
    fm = {
        "source": "900题",
        "question_id": "qid-aabbccddeeff",
        "error_tags": ["极坐标", "item, with comma"],
    }
    serialized = serialize_frontmatter(fm, ["source", "question_id", "error_tags"], "\n正文\n")
    parsed, body, key_order = parse_frontmatter(serialized)

    assert parsed == fm
    assert body == "\n正文\n"
    assert key_order == ["source", "question_id", "error_tags"]


def test_parse_frontmatter_duplicate_key_keeps_first_and_warns(capsys):
    text = "---\nsource: 900题\nsource: 660题\nquestion_id: qid-aabbccddeeff\n---\n"

    parsed, _, key_order = parse_frontmatter(text)

    assert parsed["source"] == "900题"
    assert key_order == ["source", "question_id"]
    captured = capsys.readouterr()
    assert "duplicated frontmatter key ignored: source" in captured.err


def test_parse_frontmatter_field_reuses_main_parser_for_lists():
    text = "---\nerror_tags: [极坐标, \"item, with comma\"]\n---\n"

    value = parse_frontmatter_field(text, "error_tags")

    assert value == '[极坐标, "item, with comma"]'
