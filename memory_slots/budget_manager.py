import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import json
import logging
from typing import Dict, Any, List
import httpx
import psutil
from config import EMPLOYEE_ZONE, MAX_MEMORY_GB, OLLAMA_API_URL

logger = logging.getLogger("BudgetManager")

class BudgetManager:
    def __init__(self, api_url: str = OLLAMA_API_URL):
        self.api_url = api_url.rstrip("/")

    def get_max_budget(self) -> float:
        """動態讀取最新硬體預算設定"""
        roster_path = EMPLOYEE_ZONE / "staff_roster.json"
        if roster_path.exists():
            try:
                data = json.loads(roster_path.read_text(encoding="utf-8"))
                return float(data.get("hardware_budget_gb", MAX_MEMORY_GB))
            except Exception:
                pass
        return MAX_MEMORY_GB

    def get_loaded_models(self) -> List[Dict[str, Any]]:
        """向 Ollama 查詢當前載入顯存/記憶體的模型狀態"""
        try:
            with httpx.Client(timeout=5.0) as client:
                res = client.get(f"{self.api_url}/api/ps")
                if res.status_code == 200:
                    return res.json().get("models", [])
        except Exception as e:
            logger.warning(f"無法向 Ollama 查詢模型載入狀況: {e}")
        return []

    def get_current_model_vram_gb(self) -> float:
        """計算 Ollama 當前模型總佔用顯存 (GB)"""
        models = self.get_loaded_models()
        total_bytes = sum(m.get("size_vram", 0) for m in models)
        return total_bytes / (1024 ** 3)

    def unload_model(self, model_name: str) -> bool:
        """主動將模型卸載釋放顯存 (keep_alive: 0)"""
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    f"{self.api_url}/api/generate",
                    json={"model": model_name, "keep_alive": 0}
                )
                logger.info(f"已發送模型卸載指令: {model_name}")
                return res.status_code == 200
        except Exception as e:
            logger.error(f"卸載模型 {model_name} 失敗: {e}")
            return False

    def unload_all_models(self):
        """卸載所有當前載入之模型"""
        for m in self.get_loaded_models():
            self.unload_model(m.get("name", ""))

    def ensure_budget_for_model(self, target_model: str) -> bool:
        """動態評估預算，不足時自動觸發顯存釋放"""
        max_budget = self.get_max_budget()
        sys_ram = psutil.virtual_memory()
        
        # 若系統實體可用記憶體極端不足 (< 2GB)，先清空顯存快取
        if sys_ram.available / (1024 ** 3) < 2.0:
            logger.warning("系統記憶體緊繃，主動執行全域模型清理...")
            self.unload_all_models()

        current_vram = self.get_current_model_vram_gb()
        if current_vram >= max_budget:
            logger.info(f"當前模型顯存 ({current_vram:.2f}GB) 超過上限 ({max_budget}GB)，正在卸載閒置模型...")
            for m in self.get_loaded_models():
                if m.get("name") != target_model:
                    self.unload_model(m.get("name"))
        return True