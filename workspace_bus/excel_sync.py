import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import json
from typing import Dict, Any, List
import pandas as pd
from config import DELIVERY_ZONE

class ExcelSync:
    def __init__(self):
        self.sheets_dir = DELIVERY_ZONE / "spreadsheets"
        self.sheets_dir.mkdir(parents=True, exist_ok=True)

    def extract_excel_summary(self, file_path: str) -> Dict[str, Any]:
        """解析 Excel/CSV 檔案，產生讓大模型可直接理解的資料規格描述"""
        p = Path(file_path)
        if not p.exists():
            return {"error": f"找不到檔案: {file_path}"}

        try:
            if p.suffix.lower() in [".xlsx", ".xls"]:
                excel_file = pd.ExcelFile(p)
                sheet_names = excel_file.sheet_names
                summary = {"file_name": p.name, "sheets": {}}
                
                for s in sheet_names[:3]:  # 最多分析前 3 個工作表
                    df = pd.read_excel(p, sheet_name=s, nrows=5)
                    summary["sheets"][s] = {
                        "columns": list(df.columns),
                        "row_preview": df.fillna("").to_dict(orient="records"),
                        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()}
                    }
                return summary
            elif p.suffix.lower() == ".csv":
                df = pd.read_csv(p, nrows=5)
                return {
                    "file_name": p.name,
                    "columns": list(df.columns),
                    "row_preview": df.fillna("").to_dict(orient="records"),
                    "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()}
                }
            else:
                return {"error": "不支援的試算表格式"}
        except Exception as e:
            return {"error": f"試算表解析失敗: {str(e)}"}

    def export_dataframe_to_delivery(self, data: List[Dict[str, Any]], filename: str) -> Path:
        """將清洗或計算完成的資料匯出至 03_delivery/spreadsheets/"""
        df = pd.DataFrame(data)
        out_path = self.sheets_dir / filename
        if out_path.suffix.lower() == ".csv":
            df.to_csv(out_path, index=False, encoding="utf-8-sig")
        else:
            df.to_excel(out_path, index=False)
        return out_path