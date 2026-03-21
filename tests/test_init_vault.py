"""test init_vault.py"""
import json
from helpers import run_script


def test_fresh_init(tmp_path):
    vault = tmp_path / "test_vault"
    rc, out, _ = run_script("init_vault.py", [str(vault)])
    assert rc == 0
    data = json.loads(out)
    assert len(data["created_dirs"]) > 0
    assert len(data["created_files"]) > 0
    assert (vault / "我的学习者档案.md").exists()
    assert (vault / "知识地图" / "数学一.md").exists()
    assert (vault / "知识地图" / "408.md").exists()
    assert (vault / "错题本" / "数学一").is_dir()
    assert (vault / "周计划").is_dir()


def test_idempotent(tmp_path):
    vault = tmp_path / "test_vault"
    run_script("init_vault.py", [str(vault)])
    rc, out, _ = run_script("init_vault.py", [str(vault)])
    assert rc == 0
    data = json.loads(out)
    assert len(data["created_files"]) == 0
    assert len(data["skipped_files"]) > 0


def test_force_overwrite(tmp_path):
    vault = tmp_path / "test_vault"
    run_script("init_vault.py", [str(vault)])
    rc, out, _ = run_script("init_vault.py", [str(vault), "--force"])
    assert rc == 0
    data = json.loads(out)
    assert len(data["overwritten_files"]) > 0


def test_env_var(tmp_path):
    vault = tmp_path / "env_vault"
    rc, out, _ = run_script("init_vault.py", [],
                            env_extra={"KAOYAN_OBSIDIAN_ROOT": str(vault)})
    assert rc == 0
    data = json.loads(out)
    assert (vault / "我的学习者档案.md").exists()
