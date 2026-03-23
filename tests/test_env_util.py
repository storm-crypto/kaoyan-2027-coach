"""test env_util.py"""
import os
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from env_util import (
    atomic_write,
    is_icloud_placeholder,
    json_error,
    resolve_obsidian_root,
    resolve_skill_root,
    safe_float,
    safe_int,
    split_optional_root_and_value,
)


def test_resolve_obsidian_root_prefers_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("KAOYAN_OBSIDIAN_ROOT", "/tmp/from-env")
    assert resolve_obsidian_root(str(tmp_path)) == tmp_path


def test_resolve_obsidian_root_uses_env(tmp_path, monkeypatch):
    monkeypatch.setenv("KAOYAN_OBSIDIAN_ROOT", str(tmp_path))
    assert resolve_obsidian_root() == tmp_path


def test_resolve_obsidian_root_missing_exits(monkeypatch, capsys):
    monkeypatch.delenv("KAOYAN_OBSIDIAN_ROOT", raising=False)
    with pytest.raises(SystemExit):
        resolve_obsidian_root()
    captured = capsys.readouterr()
    assert "KAOYAN_OBSIDIAN_ROOT" in captured.out


def test_resolve_skill_root_prefers_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("KAOYAN_SKILL_ROOT", "/tmp/from-env")
    assert resolve_skill_root(str(tmp_path)) == tmp_path


def test_atomic_write_overwrites_content(tmp_path):
    target = tmp_path / "note.md"
    atomic_write(target, "first")
    atomic_write(target, "second")
    assert target.read_text(encoding="utf-8") == "second"
    assert not (tmp_path / "note.md.tmp").exists()


def test_safe_int_and_safe_float_defaults():
    assert safe_int("3") == 3
    assert safe_int("oops", default=7) == 7
    assert safe_float("2.5") == 2.5
    assert safe_float("oops", default=1.2) == 1.2


def test_is_icloud_placeholder_detects_sidecar(tmp_path):
    target = tmp_path / "card.md"
    target.write_text("content", encoding="utf-8")
    placeholder = tmp_path / ".card.md.icloud"
    placeholder.write_text("", encoding="utf-8")
    assert is_icloud_placeholder(target) is True


def test_json_error_exits_with_json(capsys):
    with pytest.raises(SystemExit):
        json_error("boom")
    captured = capsys.readouterr()
    assert '"error": true' in captured.out.lower()
    assert "boom" in captured.out


def test_split_optional_root_and_value_accepts_hours_in_arg1():
    root_arg, hours_arg = split_optional_root_and_value("4", None)
    assert root_arg is None
    assert hours_arg == "4"


def test_split_optional_root_and_value_keeps_explicit_root_and_hours():
    root_arg, hours_arg = split_optional_root_and_value("/tmp/vault", "6")
    assert root_arg == "/tmp/vault"
    assert hours_arg == "6"
