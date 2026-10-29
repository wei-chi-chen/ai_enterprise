import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import json
import logging
from typing import Dict, Any, Callable
from workspace_bus.file_gateway import FileGateway
from workspace_bus.repo_indexer import RepoIndexer

logger = logging.getLogger("ReActEngine")

class ReActEngine:
    def __init__(self):
        self.gateway = FileGateway()
        self.indexer = RepoIndexer()

    def get_tool_definitions(self) -> str:
        return """可調用工具清單 (JSON 格式)：
1. {"action": "read_file", "path": "檔案相對路徑"} - 讀取專案內檔案
2. {"action": "search_symbol", "symbol": "符號名稱"} - 檢索跨檔案類別或函式定義
3. {"action": "list_files", "dir": "目錄相對路徑"} - 檢視目錄內容
若無須調用工具即可作答，請直接輸出 {"action": "finish", "final_code": "代碼本體"}"""

    def execute_tool(self, action_json: Dict[str, Any]) -> str:
        act = action_json.get("action")
        try:
            if act == "read_file":
                p = action_json.get("path", "")
                full_p = BASE_DIR / p
                if full_p.exists():
                    return full_p.read_text(encoding="utf-8")[:1500]
                return f"錯誤：找不到檔案 {p}"
            elif act == "search_symbol":
                sym = action_json.get("symbol", "")
                return self.indexer.search_symbol_context(sym)
            elif act == "list_files":
                d = action_json.get("dir", ".")
                target = BASE_DIR / d
                if target.exists():
                    items = [f.name for f in target.iterdir()]
                    return ", ".join(items[:20])
                return f"錯誤：找不到目錄 {d}"
            elif act == "finish":
                return "OK"
            else:
                return f"未知工具指令: {act}"
        except Exception as e:
            return f"工具執行異常: {e}"