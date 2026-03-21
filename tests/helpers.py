"""测试辅助函数。"""
import os
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def run_script(script_name, args=None, env_extra=None):
    """运行 scripts/ 下的脚本，返回 (returncode, stdout, stderr)。"""
    cmd = ["python3", str(SCRIPTS_DIR / script_name)] + (args or [])
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(SCRIPTS_DIR))
    return result.returncode, result.stdout, result.stderr
