import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import logging
from typing import Any, Dict
import docx
import openpyxl
import pandas as pd
from config import WORKSPACE_DIR

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("FileParser")


class FileParser:

    def __init__(self, workspace_root: Path = WORKSPACE_DIR):
        self.workspace_root = workspace_root.resolve()

    def parse(self, relative_path: str) -> Dict[str, Any]:
        """依據檔案副檔名自動轉譯為結構化文字摘要"""
        file_path = (self.workspace_root / relative_path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"找不到檔案: {relative_path}")

        ext = file_path.suffix.lower()

        if ext in [".txt", ".py", ".json", ".md", ".csv"]:
            return self._parse_text(file_path)
        elif ext in [".xlsx", ".xls"]:
            return self._parse_excel(file_path)
        elif ext in [".docx"]:
            return self._parse_docx(file_path)
        elif ext in [".png", ".jpg", ".jpeg"]:
            return self._parse_image_meta(file_path)
        else:
            return {
                "type": "binary",
                "content": f"[二進位或未知格式檔案: {file_path.name}]",
            }

    def _parse_text(self, file_path: Path) -> Dict[str, Any]:
        return {"type": "text", "content": file_path.read_text(encoding="utf-8")}

    def _parse_excel(
        self, file_path: Path, max_rows: int = 20
    ) -> Dict[str, Any]:
        """讀取 Excel 各工作表摘要與前幾筆資料"""
        try:
            excel_file = pd.ExcelFile(file_path)
            sheets_summary = {}
            for sheet in excel_file.sheet_names:
                df = pd.read_excel(file_path, sheet_name=sheet)
                sheets_summary[sheet] = {
                    "shape": df.shape,
                    "columns": list(df.columns),
                    "preview": df.head(max_rows).to_dict(orient="records"),
                }
            return {"type": "spreadsheet", "sheets": sheets_summary}
        except Exception as e:
            logger.error(f"解析 Excel 失敗: {e}")
            return {"type": "error", "content": str(e)}

    def _parse_docx(self, file_path: Path) -> Dict[str, Any]:
        """讀取 Word 段落文字與表格摘要"""
        try:
            doc = docx.Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return {"type": "document", "paragraphs": paragraphs}
        except Exception as e:
            logger.error(f"解析 Docx 失敗: {e}")
            return {"type": "error", "content": str(e)}

    def _parse_image_meta(self, file_path: Path) -> Dict[str, Any]:
        """讀取圖片基礎規格，供 Llama-Vision 模型接手"""
        from PIL import Image

        try:
            with Image.open(file_path) as img:
                return {
                    "type": "image",
                    "format": img.format,
                    "size": img.size,
                    "mode": img.mode,
                }
        except Exception as e:
            return {"type": "error", "content": str(e)}


if __name__ == "__main__":
    parser = FileParser()
    test_file = "02_任務區/active_context.md"
    print(f"測試解析文字檔: {test_file}")
    res = parser.parse(test_file)
    print("解析結果類型：", res.get("type"))
    print("FileParser 運作正常。")