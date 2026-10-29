import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import os
import tempfile
import logging
from config import WORKSPACE_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FileGateway")

class FileGateway:
    def __init__(self, workspace_root: Path = WORKSPACE_DIR):
        self.workspace_root = workspace_root.resolve()

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """驗證並解析安全路徑，嚴格防止目錄遍歷逃逸出 enterprise_workspace"""
        # 正規化路徑，避免不同作業系統分隔符號問題
        clean_rel = str(relative_path).lstrip("/\\")
        target = (self.workspace_root / clean_rel).resolve()
        
        # 檢查解析後的真實路徑是否仍在工作區根目錄之下
        if not str(target).startswith(str(self.workspace_root)):
            raise PermissionError(f"存取拒絕：路徑逃逸出工作區 -> {relative_path}")
        return target

    def read_text(self, relative_path: str) -> str:
        """安全讀取文字檔案"""
        file_path = self._resolve_safe_path(relative_path)
        if not file_path.exists():
            raise FileNotFoundError(f"檔案不存在: {relative_path}")
        return file_path.read_text(encoding="utf-8")

    def write_text(self, relative_path: str, content: str) -> Path:
        """
        使用原子寫入（Atomic Write）確保檔案完整性，
        自動建立缺失的父目錄，並回傳寫入成功的 Path 物件。
        """
        file_path = self._resolve_safe_path(relative_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        dir_path = file_path.parent
        # 在同一目錄下建立臨時檔案，確保 os.replace 屬於同一磁碟分區的原子操作
        with tempfile.NamedTemporaryFile("w", dir=dir_path, delete=False, encoding="utf-8") as tf:
            tf.write(content)
            temp_name = tf.name

        # 原子替換目標檔案
        os.replace(temp_name, file_path)
        logger.info(f"安全寫入完成: {relative_path}")
        return file_path

    def file_exists(self, relative_path: str) -> bool:
        """檢查檔案是否存在"""
        try:
            return self._resolve_safe_path(relative_path).exists()
        except PermissionError:
            return False

if __name__ == "__main__":
    gateway = FileGateway()
    test_rel_path = "02_tasks/test_gateway.txt"
    print("測試寫入檔案...")
    res_path = gateway.write_text(test_rel_path, "FileGateway 運作正常")
    print(f"實際寫入路徑：{res_path}")
    print(f"讀取驗證：{gateway.read_text(test_rel_path)}")
    # 清理測試檔
    res_path.unlink(missing_ok=True)
    print("測試完畢，暫存檔已清除。")