import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import json
import time
import base64
import logging
from typing import Any, Dict, Optional, Callable, List
import httpx
from config import OLLAMA_API_URL
from memory_slots.budget_manager import BudgetManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("OllamaClient")

class OllamaClient:
    def __init__(self, api_url: str = OLLAMA_API_URL):
        self.api_url = api_url.rstrip("/")
        self.budget_manager = BudgetManager(api_url=self.api_url)

    def generate(
        self,
        model: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        images: Optional[List[str]] = None,
        temperature: float = 0.2,
        num_ctx: Optional[int] = 8192,
        format_json: bool = False,
        timeout: float = 1800.0,
        first_token_timeout: float = 360.0,
        idle_token_timeout: float = 120.0,
        on_token: Optional[Callable[[str, int], None]] = None,
        max_retries: int = 2
    ) -> str:
        """具備冷啟動自適應、降級重試與顯存保護的推論客戶端"""
        options: Dict[str, Any] = {
            "temperature": temperature
        }
        if num_ctx:
            if "vision" in model.lower() and num_ctx > 8192:
                options["num_ctx"] = 8192
            else:
                options["num_ctx"] = num_ctx

        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": options
        }

        if system_prompt:
            payload["system"] = system_prompt

        if format_json:
            payload["format"] = "json"

        if images:
            base64_imgs = []
            for img_item in images:
                if img_item.startswith("data:image") or len(img_item) > 500:
                    raw_b64 = img_item.split(",")[-1] if "," in img_item else img_item
                    base64_imgs.append(raw_b64)
                    continue

                p = Path(img_item)
                if not p.is_absolute():
                    potential_paths = [
                        Path.cwd() / img_item,
                        BASE_DIR / img_item,
                        BASE_DIR / "enterprise_workspace" / img_item,
                        BASE_DIR / "enterprise_workspace" / "uploads" / img_item
                    ]
                    for cand in potential_paths:
                        if cand.exists():
                            p = cand
                            break

                if p.exists() and p.is_file():
                    img_bytes = p.read_bytes()
                    base64_imgs.append(base64.b64encode(img_bytes).decode("utf-8"))
                else:
                    logger.warning(f"找不到指定圖片檔案: {img_item}")

            if base64_imgs:
                payload["images"] = base64_imgs

        for attempt in range(max_retries + 1):
            try:
                if not self.budget_manager.ensure_budget_for_model(model):
                    logger.warning(f"記憶體預算警告，嘗試為 {model} 調度空間...")

                collected_text = []
                token_count = 0
                start_time = time.time()
                last_token_time = start_time

                timeout_cfg = httpx.Timeout(timeout=timeout, connect=180.0, read=360.0, write=60.0)

                with httpx.Client(timeout=timeout_cfg) as client:
                    with client.stream("POST", f"{self.api_url}/api/generate", json=payload) as response:
                        if response.status_code != 200:
                            response.read()
                            err_detail = response.text
                            raise RuntimeError(f"Ollama API 錯誤 ({response.status_code}): {err_detail}")

                        for line in response.iter_lines():
                            now = time.time()
                            
                            if token_count == 0 and (now - start_time) > first_token_timeout:
                                self.budget_manager.unload_model(model)
                                raise TimeoutError(f"模型 {model} 首字超時 ({first_token_timeout}s)")

                            if token_count > 0 and (now - last_token_time) > idle_token_timeout:
                                self.budget_manager.unload_model(model)
                                raise TimeoutError(f"模型 {model} 輸出停頓超過 {idle_token_timeout}s")

                            if not line:
                                continue

                            chunk = json.loads(line)
                            token = chunk.get("response", "")
                            if token:
                                collected_text.append(token)
                                token_count += 1
                                last_token_time = time.time()
                                if on_token:
                                    on_token(token, token_count)

                            if chunk.get("done", False):
                                break

                return "".join(collected_text).strip()

            except (TimeoutError, httpx.ReadTimeout) as e:
                logger.warning(f"模型 {model} 第 {attempt + 1} 次呼叫超時 ({e})，正在執行模型重置並重試...")
                self.budget_manager.unload_model(model)
                time.sleep(2.0)
                if attempt == max_retries:
                    raise RuntimeError(f"模型 {model} 經多次重試後仍無法完成推理: {e}")
            except Exception as e:
                logger.error(f"模型 {model} 異常: {e}")
                if attempt == max_retries:
                    raise e
                time.sleep(2.0)

        return ""