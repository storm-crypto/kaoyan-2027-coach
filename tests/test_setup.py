"""安装检查只在隔离的子进程 HOME 内运行，不触碰真实配置。"""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

SETUP = Path(__file__).resolve().parents[1] / "setup.sh"


@pytest.fixture
def setup_env(tmp_path):
    repo = tmp_path / "skill with spaces"
    repo.mkdir()
    shutil.copy2(SETUP, repo / "setup.sh")
    home = tmp_path / "isolated-user"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # 只替换子进程环境；父进程和用户的 HOME 均保持原值。
    env = {**os.environ, "HOME": str(home), "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    vault = tmp_path / "vault"
    vault.mkdir()
    env["KAOYAN_OBSIDIAN_ROOT"] = str(vault)
    return repo, home, bin_dir, env


def run_setup(context, *args):
    repo, _, _, env = context
    return subprocess.run(["/bin/bash", str(repo / "setup.sh"), *args],
                          capture_output=True, text=True, env=env)


def python_probe(context, version=(3, 9, 0), figures=False):
    """在真实版本判断表达式中注入版本；其他 Python 调用仍用实际解释器。"""
    _, _, bin_dir, _ = context
    helper = bin_dir / "probe.py"
    helper.write_text(f"""import os, sys
args = sys.argv[1:]
code = args[args.index('-c') + 1] if '-c' in args else ''
if 'sys.version_info' in code:
    sys.version_info = {version!r}
    sys.version = '.'.join(map(str, sys.version_info))
    exec(code)
elif 'find_spec' in code:
    sys.exit({0 if figures else 1})
else:
    os.execv({sys.executable!r}, [{sys.executable!r}, *args])
""", encoding="utf-8")
    command = bin_dir / "python3"
    # -B 必须交给解释器；只作为 helper 的参数会让 macOS 在隔离 HOME 写 pyc 缓存。
    command.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} -B {shlex.quote(str(helper))} \"$@\"\n", encoding="utf-8")
    command.chmod(0o755)


def links(context):
    return [context[1] / tool / "skills/kaoyan-2027-coach" for tool in (".claude", ".codex")]


@pytest.mark.parametrize("version,accepted", [((3, 8, 20), False), ((3, 9, 0), True), ((4, 0, 0), True)])
def test_python_minimum_is_enforced_before_creating_links(setup_env, version, accepted):
    python_probe(setup_env, version)
    result = run_setup(setup_env)
    assert result.returncode == (0 if accepted else 1), (result.stdout, result.stderr)
    assert all(link.is_symlink() == accepted for link in links(setup_env))
    if not accepted:
        assert "需要 Python 3.9+" in result.stdout
        assert list(setup_env[1].iterdir()) == []


def test_missing_python_is_reported_without_changes(setup_env):
    _, home, bin_dir, env = setup_env
    (bin_dir / "dirname").symlink_to(shutil.which("dirname"))
    env["PATH"] = str(bin_dir)
    result = run_setup(setup_env)
    assert result.returncode == 1
    assert "未找到 python3" in result.stdout
    assert list(home.iterdir()) == []


def test_check_on_fresh_install_is_read_only(setup_env):
    python_probe(setup_env)
    result = run_setup(setup_env, "--check")
    assert result.returncode == 1
    assert result.stdout.count("[MISSING]") == 2
    assert list(setup_env[1].iterdir()) == []


def test_successful_install_and_relative_links_pass_read_only_check(setup_env):
    python_probe(setup_env)
    result = run_setup(setup_env)
    assert result.returncode == 0, result.stderr
    assert "[OPTIONAL]" in result.stdout  # 配图依赖缺失不阻止普通使用。
    repo = setup_env[0]
    for link in links(setup_env):
        assert link.resolve() == repo
        link.unlink()
        link.symlink_to(os.path.relpath(repo, link.parent), target_is_directory=True)
    before = [(os.readlink(link), link.lstat().st_mtime_ns) for link in links(setup_env)]
    result = run_setup(setup_env, "--check")
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "没有修改链接或配置" in result.stdout
    assert before == [(os.readlink(link), link.lstat().st_mtime_ns) for link in links(setup_env)]
    result = run_setup(setup_env)
    assert result.returncode == 0
    assert before == [(os.readlink(link), link.lstat().st_mtime_ns) for link in links(setup_env)]


@pytest.mark.parametrize("broken", [True, False])
@pytest.mark.parametrize("check_only", [True, False])
def test_wrong_or_broken_link_is_preserved_and_blocks_partial_install(setup_env, broken, check_only):
    python_probe(setup_env)
    first, second = links(setup_env)
    first.parent.mkdir(parents=True)
    target = setup_env[1] / "different-skill"
    if not broken:
        target.mkdir()
    first.symlink_to(target, target_is_directory=True)
    result = run_setup(setup_env, *("--check",) if check_only else ())
    assert result.returncode == 1
    assert ("链接已失效" if broken else "链接指向其他位置") in result.stdout
    assert os.readlink(first) == str(target)
    assert not second.exists() and not second.is_symlink()
    assert not second.parent.exists()


@pytest.mark.parametrize("directory", [True, False])
def test_real_file_or_directory_is_never_replaced(setup_env, directory):
    python_probe(setup_env)
    first, second = links(setup_env)
    first.parent.mkdir(parents=True)
    if directory:
        first.mkdir()
        marker = first / "private-note.md"
    else:
        marker = first
    marker.write_text("keep original", encoding="utf-8")
    result = run_setup(setup_env)
    assert result.returncode == 1
    assert "实际文件或目录" in result.stdout
    assert marker.read_text() == "keep original"
    assert not first.is_symlink()
    assert not second.parent.exists()


def test_check_reports_unconfigured_vault_but_install_can_precede_configuration(setup_env):
    python_probe(setup_env)
    setup_env[3].pop("KAOYAN_OBSIDIAN_ROOT")
    assert run_setup(setup_env).returncode == 0
    result = run_setup(setup_env, "--check")
    assert result.returncode == 1
    assert "尚未配置 KAOYAN_OBSIDIAN_ROOT" in result.stdout


def test_missing_vault_is_not_created_by_install_or_check(setup_env):
    python_probe(setup_env)
    path = setup_env[0] / "new-vault"
    setup_env[3]["KAOYAN_OBSIDIAN_ROOT"] = str(path)
    assert run_setup(setup_env).returncode == 0
    result = run_setup(setup_env, "--check")
    assert result.returncode == 1
    assert "学习库尚未创建" in result.stdout
    assert not path.exists()


def test_vault_path_cannot_be_a_file(setup_env):
    python_probe(setup_env)
    path = setup_env[0] / "notes.md"
    path.write_text("keep this file")
    setup_env[3]["KAOYAN_OBSIDIAN_ROOT"] = str(path)
    result = run_setup(setup_env)
    assert result.returncode == 1
    assert "不是目录" in result.stdout
    assert path.read_text() == "keep this file"
    assert all(not link.is_symlink() for link in links(setup_env))
