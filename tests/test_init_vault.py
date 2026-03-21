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


def test_profile_bootstrap_args(tmp_path):
    vault = tmp_path / "bootstrap_vault"
    rc, out, _ = run_script("init_vault.py", [
        str(vault),
        "--school-major", "浙大计算机",
        "--target-total", "380",
        "--exam-date", "2026-12-20",
        "--daily-hours", "7",
        "--stage", "强化冲刺期",
    ])
    assert rc == 0
    data = json.loads(out)
    assert "目标院校/专业" in data["profile_updated_fields"]
    content = (vault / "我的学习者档案.md").read_text(encoding="utf-8")
    assert "浙大计算机" in content
    assert "380" in content
    assert "2026-12-20" in content
    assert "7" in content
    assert "强化冲刺期" in content


def test_profile_bootstrap_only_fills_blanks_without_force(tmp_path):
    vault = tmp_path / "bootstrap_existing"
    run_script("init_vault.py", [str(vault), "--school-major", "一志愿A", "--target-total", "360"])
    rc, out, _ = run_script("init_vault.py", [
        str(vault),
        "--school-major", "一志愿B",
        "--target-total", "380",
        "--daily-hours", "6",
    ])
    assert rc == 0
    content = (vault / "我的学习者档案.md").read_text(encoding="utf-8")
    assert "一志愿A" in content
    assert "380" not in content
    assert "6" in content
