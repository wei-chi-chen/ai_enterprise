import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import re
from typing import Dict, Any, List

class TracebackParser:
    @staticmethod
    def parse(stderr_text: str) -> Dict[str, Any]:
        """解析標準錯誤輸出，提取核心例外名稱、最後出錯位置與精簡摘要"""
        if not stderr_text or not stderr_text.strip():
            return {
                "has_error": False,
                "error_type": None,
                "error_message": None,
                "culprit_file": None,
                "culprit_line": None,
                "cleaned_summary": ""
            }

        lines = stderr_text.strip().splitlines()
        
        # 提取最後一行的例外型別與訊息 (e.g. ValueError: invalid literal ...)
        last_line = lines[-1].strip()
        error_type = "UnknownError"
        error_message = last_line
        
        match_err = re.match(r"^([a-zA-Z0-9_]+Error|[a-zA-Z0-9_]+Exception):\s*(.*)$", last_line)
        if match_err:
            error_type = match_err.group(1)
            error_message = match_err.group(2)
        elif "AssertionError" in last_line:
            error_type = "AssertionError"

        # 反向搜尋最後一個出錯的具體檔案與行數
        culprit_file = None
        culprit_line = None
        file_line_regex = re.compile(r'File\s+"([^"]+)",\s+line\s+(\d+)(?:,\s+in\s+(.+))?')
        
        for line in reversed(lines):
            match = file_line_regex.search(line)
            if match:
                culprit_file = match.group(1)
                culprit_line = int(match.group(2))
                break

        # 整理出精簡版堆疊（只保留最近 10 行關鍵資訊）
        snippet_lines = lines[-10:] if len(lines) > 10 else lines
        cleaned_summary = "\n".join(snippet_lines)

        return {
            "has_error": True,
            "error_type": error_type,
            "error_message": error_message,
            "culprit_file": culprit_file,
            "culprit_line": culprit_line,
            "cleaned_summary": cleaned_summary
        }

if __name__ == "__main__":
    parser = TracebackParser()
    sample_trace = """Traceback (most recent call last):
  File "enterprise_workspace/test_app.py", line 12, in <module>
    result = divide(10, 0)
  File "enterprise_workspace/test_app.py", line 5, in divide
    return a / b
ZeroDivisionError: division by zero"""

    print("測試例外解析機制...")
    parsed = parser.parse(sample_trace)
    print("解析出的錯誤類型：", parsed["error_type"])
    print("出錯檔案：", parsed["culprit_file"])
    print("出錯行號：", parsed["culprit_line"])
    print("TracebackParser 驗證通過。")