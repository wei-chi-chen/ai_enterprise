import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import ast
from typing import Dict, List, Any

class RepoIndexer:
    def __init__(self, root_dir: Path = BASE_DIR):
        self.root_dir = root_dir

    def scan_symbols(self) -> Dict[str, List[Dict[str, Any]]]:
        """掃描全專案所有 Python 原始碼，萃取函式與類別定義索引"""
        symbol_index = {}
        for py_path in self.root_dir.rglob("*.py"):
            # 排除虛擬環境與快取
            if any(part in py_path.parts for part in ["venv", "__pycache__", ".git"]):
                continue
            try:
                content = py_path.read_text(encoding="utf-8")
                tree = ast.parse(content)
                rel_path = str(py_path.relative_to(self.root_dir)).replace("\\", "/")
                symbols = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        symbols.append({"type": "function", "name": node.name, "lineno": node.lineno})
                    elif isinstance(node, ast.ClassDef):
                        symbols.append({"type": "class", "name": node.name, "lineno": node.lineno})
                if symbols:
                    symbol_index[rel_path] = symbols
            except Exception:
                pass
        return symbol_index

    def search_symbol_context(self, symbol_name: str) -> str:
        """尋找指定符號在全專案中的定義位置與周邊代碼"""
        index = self.scan_symbols()
        findings = []
        for file_path, syms in index.items():
            for s in syms:
                if symbol_name.lower() in s["name"].lower():
                    findings.append(f"- 檔案 `{file_path}` 第 {s['lineno']} 行定義了 {s['type']} `{s['name']}`")
        if not findings:
            return f"專案內未找到與 `{symbol_name}` 相關的符號定義。"
        return "【跨檔案符號關聯檢索結果】：\n" + "\n".join(findings)