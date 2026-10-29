import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import subprocess
import time
import logging
import psutil

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FileUnlocker")

class FileUnlocker:
    """處理 Windows 檔案排他鎖釋放與阻礙行程清理"""

    @staticmethod
    def kill_processes_by_name(process_names: list[str]) -> None:
        """強制結束佔用辦公檔案的指定程式（如 EXCEL.EXE、WINWORD.EXE）"""
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and proc.info['name'].upper() in [p.upper() for p in process_names]:
                    logger.warning(f"偵測到鎖定行程 {proc.info['name']} (PID: {proc.info['pid']})，執行終止...")
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    @staticmethod
    def safe_execute_with_retry(action_fn, max_retries: int = 3, retry_delay: float = 1.0):
        """帶重試機制的檔案操作包裝器，遇 WinError 32 自動釋放常用鎖定並重試"""
        for attempt in range(1, max_retries + 1):
            try:
                return action_fn()
            except PermissionError as e:
                logger.warning(f"檔案被佔用 (嘗試 {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    # 釋放可能佔用 Excel 或 Word 檔案的背景殘留行程
                    FileUnlocker.kill_processes_by_name(["EXCEL.EXE", "WINWORD.EXE"])
                    time.sleep(retry_delay)
                else:
                    raise e

if __name__ == "__main__":
    unlocker = FileUnlocker()
    print("測試鎖定檢查機制...")
    # 測試執行無例外動作
    unlocker.safe_execute_with_retry(lambda: print("執行正常操作成功"))
    print("FileUnlocker 測試通過。")