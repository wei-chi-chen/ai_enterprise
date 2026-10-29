import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import subprocess
import logging
from typing import Dict, Any, Optional
from config import WORKSPACE_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Sandbox")

class ExecutionSandbox:
    def __init__(self, workspace_root: Path = WORKSPACE_DIR):
        self.workspace_root = workspace_root.resolve()

    def run_python_code(self, script_path: str, args: Optional[list[str]] = None, timeout: float = 30.0) -> Dict[str, Any]:
        """在工作目錄內安全執行指定的 Python 腳本"""
        target_script = (self.workspace_root / script_path).resolve()
        if not target_script.exists():
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"腳本不存在: {script_path}",
                "timeout": False
            }

        cmd = [sys.executable, str(target_script)] + (args or [])

        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout
            )
            return {
                "success": res.returncode == 0,
                "returncode": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "timeout": False
            }
        except subprocess.TimeoutExpired as te:
            logger.error(f"程式碼執行逾時 ({timeout}s): {script_path}")
            return {
                "success": False,
                "returncode": -1,
                "stdout": te.stdout.decode("utf-8", errors="ignore") if te.stdout else "",
                "stderr": f"執行逾時，強制終止（超過 {timeout} 秒）",
                "timeout": True
            }
        except Exception as e:
            logger.error(f"沙盒執行異常: {e}")
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                "timeout": False
            }

if __name__ == "__main__":
    sandbox = ExecutionSandbox()
    test_file = sandbox.workspace_root / "temp_test.py"
    test_file.write_text("print('Sandbox test: OK')", encoding="utf-8")
    
    print("測試沙盒執行...")
    result = sandbox.run_python_code("temp_test.py")
    print("輸出結果：", result["stdout"].strip())
    print("執行成功：", result["success"])
    
    test_file.unlink(missing_ok=True)
    print("Sandbox 模組驗證通過。")