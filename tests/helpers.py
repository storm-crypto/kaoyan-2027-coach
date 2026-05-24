"""测试辅助函数。"""
import os
import subprocess
import sys
from datetime import date as _date
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))
from log_layout import log_path_for as _log_path_for  # noqa: E402


def log_path(vault_root, day):
    """返回新结构下指定日期的学习日志路径，并确保父目录存在。
    day 可传 'YYYY-MM-DD' 字符串或 date 对象。"""
    if isinstance(day, str):
        day = _date.fromisoformat(day)
    p = _log_path_for(vault_root, day)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def run_script(script_name, args=None, env_extra=None):
    """运行 scripts/ 下的脚本，返回 (returncode, stdout, stderr)。"""
    cmd = ["python3", str(SCRIPTS_DIR / script_name)] + (args or [])
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(SCRIPTS_DIR))
    return result.returncode, result.stdout, result.stderr
