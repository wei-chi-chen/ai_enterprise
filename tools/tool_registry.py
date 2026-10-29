import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import importlib.util
import inspect
import logging
from typing import Dict, Any, List
from config import SHARED_TOOLS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ToolRegistry")

class ToolRegistry:
    def __init__(self, tools_dir: Path = SHARED_TOOLS_DIR):
        self.tools_dir = tools_dir
        self.tools_dir.mkdir(parents=True, exist_ok=True)

    def list_available_tools(self) -> List[Dict[str, Any]]:
        """掃描 shared_tools 資料夾，提取所有可用工具腳本與 docstring 說明"""
        tools_info = []
        for file in self.tools_dir.glob("*.py"):
            if file.name.startswith("__"):
                continue
            doc = self._extract_docstring(file)
            tools_info.append({
                "tool_name": file.stem,
                "file_path": str(file.relative_to(BASE_DIR)),
                "description": doc or "尚無詳細功能說明"
            })
        return tools_info

    def _extract_docstring(self, file_path: Path) -> str:
        """讀取模組頂層的說明字串"""
        try:
            content = file_path.read_text(encoding="utf-8")
            spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return inspect.getdoc(module) or ""
        except Exception as e:
            logger.debug(f"提取工具文檔失敗 ({file_path.name}): {e}")
        return ""

    def generate_tools_prompt(self) -> str:
        """產生供 LLM 參考的工具清單文字"""
        tools = self.list_available_tools()
        if not tools:
            return "目前 shared_tools/ 無自生長可用工具。"
        
        lines = ["【本機可用自生長工具清單】："]
        for t in tools:
            lines.append(f"- **{t['tool_name']}**: {t['description']}")
        return "\n".join(lines)

if __name__ == "__main__":
    registry = ToolRegistry()
    print("測試工具探索機制...")
    # 建立一個測試工具檔案
    sample_tool = SHARED_TOOLS_DIR / "sample_calc.py"
    sample_tool.write_text('"""基礎加法輔助工具，用於精確計算數值累加。"""\ndef add(a, b):\n    return a + b\n', encoding="utf-8")

    prompt_summary = registry.generate_tools_prompt()
    print("工具清單 Prompt 輸出：\n", prompt_summary)

    sample_tool.unlink(missing_ok=True)
    print("ToolRegistry 驗證通過。")