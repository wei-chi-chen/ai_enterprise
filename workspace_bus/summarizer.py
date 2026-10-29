import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import logging
from config import TASK_ZONE
from memory_slots.ollama_client import OllamaClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Summarizer")

class Summarizer:
    def __init__(self, secretary_model: str = "qwen2.5:7b"):
        self.secretary_model = secretary_model
        self.active_context_file = TASK_ZONE / "active_context.md"
        self.ollama_client = OllamaClient()

    def update_context(self, current_task_title: str, execution_log: str, is_success: bool) -> str:
        """依據最新執行步驟的日誌，調用 7B 模型生成滾動進度並更新 active_context.md"""
        existing_context = ""
        if self.active_context_file.exists():
            existing_context = self.active_context_file.read_text(encoding="utf-8")

        prompt = f"""請以「秘書與摘要助理」的職責，整合專案最新進度並更新滾動摘要。
保持簡明精確，提取關鍵結論、產出檔案與待解決問題。

【歷史現況】：
{existing_context[-1500:] if len(existing_context) > 1500 else existing_context}

【最新步驟】：{current_task_title}
【執行狀態】：{'成功' if is_success else '失敗/需調整'}
【最新日誌】：
{execution_log[-1200:] if len(execution_log) > 1200 else execution_log}

請直接輸出繁體中文 Markdown 格式的更新摘要，包含：
1. 當前已完成重點
2. 目前系統狀態
3. 下一步待辦
"""
        system_prompt = "你是一位精煉高效的研發秘書，只輸出結構化的專案滾動現況 Markdown，不加任何開場白與結語。"
        
        try:
            summary = self.ollama_client.generate(
                model=self.secretary_model,
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.1
            )
            self.active_context_file.write_text(summary, encoding="utf-8")
            logger.info("active_context.md 滾動摘要已更新。")
            return summary
        except Exception as e:
            logger.error(f"生成滾動摘要失敗: {e}")
            fallback_text = f"# 滾動現況\n- 最近步驟：{current_task_title} ({'成功' if is_success else '失敗'})\n"
            self.active_context_file.write_text(fallback_text, encoding="utf-8")
            return fallback_text

if __name__ == "__main__":
    summarizer = Summarizer()
    print("測試滾動摘要寫入...")
    res = summarizer.update_context(
        current_task_title="測試任務步驟",
        execution_log="測試日誌：模組正常載入，所有單元測試通過。",
        is_success=True
    )
    print("更新結果預覽：\n", res)