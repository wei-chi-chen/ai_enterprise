import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import json
import re
import ast
import time
import shutil
import logging
import threading
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import httpx

from config import WORKSPACE_DIR, TASK_ZONE, DELIVERY_ZONE, HISTORY_ZONE, EMPLOYEE_ZONE, OLLAMA_API_URL
from agents.employee import EnterpriseStaffManager
from workspace_bus.file_gateway import FileGateway
from workspace_bus.git_vcs import GitVCS
from workspace_bus.summarizer import Summarizer
from workspace_bus.metrics_collector import MetricsCollector
from workspace_bus.repo_indexer import RepoIndexer
from execution.sandbox import ExecutionSandbox
from execution.traceback_parser import TracebackParser
from tools.tool_registry import ToolRegistry

from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, SpinnerColumn
from rich.console import Console

console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("EnterpriseDaemon")

task_queue_lock = threading.Lock()
status_file_lock = threading.Lock()
CONTROL_FILE = TASK_ZONE / "daemon_control.json"
MEM_USAGE_FILE = TASK_ZONE / "memory_usage.json"
STATUS_FILE = EMPLOYEE_ZONE / "employee_status.json"

MODEL_MEMORY_MAP = {
    "qwen2.5:32b": 20.0,
    "qwen2.5-coder:32b": 20.0,
    "qwen2.5-coder:14b": 9.5,
    "llava:latest": 7.0,
    "llama3.2-vision:11b": 8.0,
    "llama3.1:8b": 6.0,
    "qwen2.5:7b": 5.5
}

STAFF_MODEL_MEM = {
    "EMP-01": 20.0,
    "EMP-02": 20.0,
    "EMP-03": 20.0,
    "EMP-04": 9.5,
    "EMP-05": 9.5,
    "EMP-06": 9.5,
    "EMP-07": 5.5,
    "EMP-08": 7.0,
    "EMP-09": 6.0,
    "EMP-10": 6.0,
    "EMP-11": 5.5,
    "EMP-12": 5.5
}

def is_valid_python(code_str: str) -> bool:
    if not code_str or len(code_str.strip()) < 15:
        return False
    if "修復後的" in code_str or "完整代碼" in code_str:
        return False
    try:
        ast.parse(code_str)
        return True
    except SyntaxError:
        return False

class EnterpriseDaemon:
    def __init__(self):
        self.gateway = FileGateway()
        self.vcs = GitVCS()
        self.sandbox = ExecutionSandbox()
        self.parser = TracebackParser()
        self.summarizer = Summarizer()
        self.metrics = MetricsCollector()
        self.indexer = RepoIndexer()
        self.registry = ToolRegistry()
        self.staff = EnterpriseStaffManager()
        self.backlog_file = TASK_ZONE / "task_backlog.json"
        self.lessons_file = HISTORY_ZONE / "lessons_learned.json"
        
        self.employee_locks = {f"EMP-{i:02d}": threading.Lock() for i in range(1, 13)}
        
        self.purge_dirty_task_folders()
        self._ensure_lessons_repo()
        self._init_control_flag()
        self._resume_interrupted_tasks()
        self.sync_realtime_memory()

    def purge_dirty_task_folders(self):
        """啟動時自動掃描並清理 02_tasks 中殘留的半成品專案資料夾"""
        tasks_dir = TASK_ZONE
        preserved_files = {
            "task_backlog.json", "active_context.md", "daemon_control.json",
            "memory_usage.json", "daemon.pid", ".gitkeep"
        }
        cleaned_count = 0
        if tasks_dir.exists():
            for item in tasks_dir.iterdir():
                if item.name not in preserved_files:
                    try:
                        if item.is_dir():
                            shutil.rmtree(item)
                            cleaned_count += 1
                        elif item.is_file() and not item.name.startswith("."):
                            item.unlink()
                            cleaned_count += 1
                    except Exception as e:
                        logger.warning(f"清理殘留項目失敗 {item.name}: {e}")
        if cleaned_count > 0:
            console.print(f"[dim yellow]🧹 已自動清理上次殘留的 {cleaned_count} 個中繼暫存項目[/dim yellow]")

    def _init_control_flag(self):
        try:
            CONTROL_FILE.write_text(json.dumps({"stop_requested": False, "is_running": True}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def is_stop_requested(self) -> bool:
        if CONTROL_FILE.exists():
            try:
                data = json.loads(CONTROL_FILE.read_text(encoding="utf-8"))
                return data.get("stop_requested", False)
            except Exception:
                return False
        return False

    def get_hardware_budget(self) -> float:
        roster_file = EMPLOYEE_ZONE / "staff_roster.json"
        if roster_file.exists():
            try:
                data = json.loads(roster_file.read_text(encoding="utf-8"))
                return float(data.get("hardware_budget_gb", 40.0))
            except Exception:
                pass
        return 40.0

    def sync_realtime_memory(self) -> float:
        total_used = 0.0
        ollama_synced = False

        try:
            url = f"{OLLAMA_API_URL.rstrip('/')}/api/ps"
            with httpx.Client(timeout=2.0) as client:
                res = client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    models = data.get("models", [])
                    bytes_used = 0
                    for m in models:
                        bytes_used += m.get("size_vram", 0) or m.get("size", 0)
                    total_used = bytes_used / (1024 ** 3)
                    ollama_synced = True
        except Exception:
            pass

        if not ollama_synced:
            with status_file_lock:
                if STATUS_FILE.exists():
                    try:
                        statuses = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
                        for emp_id, info in statuses.items():
                            if info.get("status") == "working":
                                total_used += STAFF_MODEL_MEM.get(emp_id, 8.0)
                    except Exception:
                        pass

        try:
            MEM_USAGE_FILE.write_text(json.dumps({"used_memory_gb": round(total_used, 1)}), encoding="utf-8")
        except Exception:
            pass
        return total_used

    def _ensure_lessons_repo(self):
        if not self.lessons_file.exists():
            self.lessons_file.write_text("[]", encoding="utf-8")

    def _resume_interrupted_tasks(self):
        with task_queue_lock:
            try:
                if not self.backlog_file.exists():
                    return
                tasks = json.loads(self.backlog_file.read_text(encoding="utf-8"))
                has_changes = False
                for t in tasks:
                    if t.get("status") == "processing":
                        t["status"] = "pending"
                        has_changes = True
                if has_changes:
                    self.backlog_file.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                logger.warning(f"檢查中斷任務失敗: {e}")

    def get_lessons_context(self) -> str:
        try:
            data = json.loads(self.lessons_file.read_text(encoding="utf-8"))
            if not data:
                return ""
            rules = [f"- {item.get('rule')}" for item in data[-5:]]
            return "【歷史避坑經驗（嚴格遵守）】：\n" + "\n".join(rules)
        except Exception:
            return ""

    def append_lesson(self, task_id: str, pattern: str, lesson_rule: str):
        try:
            data = json.loads(self.lessons_file.read_text(encoding="utf-8"))
            data.append({
                "task_id": task_id,
                "error_pattern": pattern,
                "rule": lesson_rule,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })
            self.lessons_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"記錄歷史教訓失敗: {e}")

    def clean_task_zone(self, paths: list):
        for p_str in paths:
            p = WORKSPACE_DIR / p_str
            if p.exists():
                try:
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
                except Exception:
                    pass

    def peek_next_pending_task(self):
        with task_queue_lock:
            if not self.backlog_file.exists():
                return None
            try:
                tasks = json.loads(self.backlog_file.read_text(encoding="utf-8"))
                for t in tasks:
                    if t.get("status") == "pending":
                        return t
                return None
            except Exception:
                return None

    def mark_task_processing(self, task_id: str):
        with task_queue_lock:
            try:
                tasks = json.loads(self.backlog_file.read_text(encoding="utf-8"))
                for t in tasks:
                    if t.get("task_id") == task_id:
                        t["status"] = "processing"
                self.backlog_file.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

    def update_task_status(self, task_id: str, new_status: str):
        with task_queue_lock:
            try:
                tasks = json.loads(self.backlog_file.read_text(encoding="utf-8"))
                for t in tasks:
                    if t.get("task_id") == task_id:
                        t["status"] = new_status
                self.backlog_file.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                logger.error(f"更新任務狀態失敗: {e}")

    # ================= 階段 1：EMP-01 獨佔規劃 =================
    def plan_architecture_and_context(self, task: dict) -> dict:
        task_id = task["task_id"]
        title = task["title"]
        desc = task["description"]
        image_path = task.get("image_path", None)
        is_project_task = task.get("is_project", False)

        console.rule(f"[bold cyan]🎯 [{task_id}] 架構規劃階段 (EMP-01 獨佔工作)[/bold cyan]")
        self.mark_task_processing(task_id)
        lessons_prompt = self.get_lessons_context()

        if image_path:
            img_file = None
            potential_paths = [
                Path(image_path),
                BASE_DIR / image_path,
                WORKSPACE_DIR / image_path,
                WORKSPACE_DIR / "uploads" / image_path
            ]
            for p in potential_paths:
                if p.exists() and p.is_file():
                    img_file = p.resolve()
                    break

            if img_file and img_file.exists():
                console.print(f"[bold magenta]👁 [{task_id}] 偵測到視覺輸入 [{img_file.name}]，調用 EMP-08 初次解析...[/bold magenta]")
                current_vision_ctx = 4096
                vision_analysis = None
                ve_msg = ""
                
                with self.employee_locks["EMP-08"]:
                    try:
                        self.sync_realtime_memory()
                        emp08 = self.staff.get_employee("EMP-08")
                        vision_analysis = emp08.work(
                            "請詳細分析此影像內容，萃取圖表數據、數值趨勢與結構規格，轉化為 Python 代碼開發規格：",
                            current_task_id=task_id,
                            action_name="視覺解析圖表特徵",
                            images=[str(img_file)],
                            temperature=0.1,
                            num_ctx=current_vision_ctx
                        )
                    except Exception as ve:
                        ve_msg = str(ve)
                        logger.warning(f"[{task_id}] EMP-08 初次視覺解析受阻: {ve}，啟動主管動態裁決...")
                    finally:
                        self.sync_realtime_memory()

                if not vision_analysis:
                    console.print(f"[bold yellow]▲ [{task_id}] 視覺分析異常，移交 EMP-01 架構主管進行 Context 調整與接管評估...[/bold yellow]")
                    with self.employee_locks["EMP-01"]:
                        emp01 = self.staff.get_employee("EMP-01")
                        arbitrate_prompt = f"""專員 EMP-08 解析圖檔 `{img_file.name}` 失敗。
任務需求：{title} - {desc}
初始 Context：{current_vision_ctx}
底層異常：{ve_msg[:300]}

請作為架構主管評估：
1. 是否需拉高 Context Length 重試解析？若需要，請推薦擴充後的 Context（如 8192 或 16384）。
2. 若評估判定模型已達硬體瓶頸，請直接親自為此圖表任務推導一份嚴謹的數據結構與假資料規格書。

輸出嚴格 JSON：
{{
  "action": "retry_with_expanded_context",
  "suggested_vision_ctx": 8192,
  "supervisor_specs": "若接管，請在此輸出專業規格推導與數據結構"
}}"""
                        try:
                            self.sync_realtime_memory()
                            arb_raw = emp01.work(
                                arbitrate_prompt,
                                current_task_id=task_id,
                                action_name="仲裁視覺 Context 與架構接管",
                                temperature=0.1,
                                num_ctx=16384,
                                format_json=True
                            )
                            arb_decision = json.loads(arb_raw)
                        except Exception as ae:
                            logger.error(f"[{task_id}] 主管仲裁失敗: {ae}")
                            arb_decision = {"action": "supervisor_takeover", "supervisor_specs": "由架構主管預設數據架構接管。"}
                        finally:
                            self.sync_realtime_memory()

                    if arb_decision.get("action") == "retry_with_expanded_context":
                        new_ctx = int(arb_decision.get("suggested_vision_ctx", 8192))
                        console.print(f"[bold green]✔ 主管裁定：將 EMP-08 Context 視窗動態擴充至 {new_ctx} tokens 重新解析！[/bold green]")
                        with self.employee_locks["EMP-08"]:
                            try:
                                self.sync_realtime_memory()
                                emp08 = self.staff.get_employee("EMP-08")
                                vision_analysis = emp08.work(
                                    "請以擴充後的 Context 深度分析影像圖表數據趨勢與代碼介面：",
                                    current_task_id=task_id,
                                    action_name=f"擴充 Context ({new_ctx}) 二次解析",
                                    images=[str(img_file)],
                                    temperature=0.1,
                                    num_ctx=new_ctx
                                )
                                desc = desc + f"\n【EMP-08 視覺感知報告 (主管擴充 {new_ctx} tokens)】：\n{vision_analysis}\n"
                            except Exception as retry_err:
                                console.print(f"[bold red]✘ 擴充後依然失敗，由主管接管規格制定。[/bold red]")
                                desc = desc + f"\n【架構主管接管圖表規格】：\n{arb_decision.get('supervisor_specs', '')}\n"
                            finally:
                                self.sync_realtime_memory()
                    else:
                        console.print(f"[bold cyan]✔ 主管裁定：由 EMP-01 親自制定圖表結構規格接管開發。[/bold cyan]")
                        desc = desc + f"\n【EMP-01 架構主管裁定規格】：\n{arb_decision.get('supervisor_specs', '')}\n"
                else:
                    desc = desc + f"\n【EMP-08 視覺感知報告】：\n{vision_analysis}\n"

        clean_name = task_id.lower().replace("-", "_")
        
        contract_prompt = f"""請針對任務制定【專案檔案樹】、【模組職責】、【嚴格 TDD 驗收測試】並【自主決定所需 Context Length】：
任務名稱：{title}
任務核心需求：{desc}
任務類型：{'多檔案專案 (Multi-File Project)' if is_project_task else '單模組工具'}
{lessons_prompt}

【重要品質、路徑與測試規範（必須嚴格遵守）】：
1. 【跨模組路徑固定】：test_file 腳本第 1~3 行必須強制包含：
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path(__file__).parent))
2. 【浮點數與演算法斷言】：所有涉數值計算、統計（如 Z-Score、標準差、均值、IQR 離群值）的測試，嚴禁直接寫死不可達的單一答案。必須：
   - 使用 `import math; assert math.isclose(a, b, abs_tol=1e-2)`。
   - 針對離群值過濾（remove_outliers），測試資料必須設置極其明顯的離群值（如正常值 10~15，離群值 1000），避免四分位插值微小差異造成誤判。
3. 【依賴庫約束】：僅限使用 Python 內建標準庫（math, json, re, typing, dataclasses, hashlib 等）以及專案宣告庫（pandas, openpyxl, matplotlib）。嚴禁 import 未安裝庫（如 cv2 等）。
4. 【真實 TDD】：golden_test_code 必須包含真實測試，嚴格驗證任務函式與邊界條件，禁止只寫 pass 或 assert True。
5. 【明確檔案規格】：files 內每個檔案的 instruction 必須完整列出需要實作的具體類別名、函式名、參數簽名與邏輯。

輸出嚴格 JSON：
{{
  "suggested_num_ctx": 16384,
  "is_multi_file": {str(is_project_task).lower()},
  "project_dir": "02_tasks/{clean_name}_proj",
  "files": [
    {{
      "filename": "{clean_name}_module.py",
      "instruction": "完整實作模組函式與介面規格"
    }}
  ],
  "test_file": "02_tasks/{clean_name}_proj/test_suite.py",
  "golden_test_code": "import sys\\nfrom pathlib import Path\\nsys.path.insert(0, str(Path(__file__).parent))\\nimport math\\nassert True\\n"
}}"""
        with self.employee_locks["EMP-01"]:
            emp01 = self.staff.get_employee("EMP-01")
            try:
                self.sync_realtime_memory()
                contract_raw = emp01.work(
                    contract_prompt, 
                    current_task_id=task_id,
                    action_name="評估架構與 Context",
                    temperature=0.1, 
                    num_ctx=16384, 
                    format_json=True
                )
                contract = json.loads(contract_raw)
            except Exception as e:
                logger.warning(f"[{task_id}] 架構決策退回標準模板: {e}")
                contract = {
                    "suggested_num_ctx": 8192,
                    "is_multi_file": is_project_task,
                    "project_dir": f"02_tasks/{clean_name}_proj",
                    "files": [{"filename": f"{clean_name}_module.py", "instruction": f"嚴格實現：{desc}"}],
                    "test_file": f"02_tasks/{clean_name}_proj/test_suite.py",
                    "golden_test_code": f"import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parent))\nimport math\nfrom {clean_name}_module import *\nassert True\n"
                }
            finally:
                self.sync_realtime_memory()

        decided_ctx = min(max(int(contract.get("suggested_num_ctx", 8192)), 4096), 65536)
        console.print(f"[bold cyan]🧠 [{task_id}] 模型自主選定 Context 視窗: {decided_ctx} tokens[/bold cyan]")

        proj_dir = contract.get("project_dir", f"02_tasks/{clean_name}_proj")
        test_file = contract.get("test_file", f"{proj_dir}/test_suite.py")
        golden_test = contract.get("golden_test_code", "assert True\n")
        self.gateway.write_text(test_file, golden_test)

        console.print(f"[dim]✔ [{task_id}] 架構規劃完畢，EMP-01 釋放就緒[/dim]")

        return {
            "task": task,
            "contract": contract,
            "decided_ctx": decided_ctx,
            "proj_dir": proj_dir,
            "test_file": test_file,
            "golden_test": golden_test,
            "clean_name": clean_name,
            "desc": desc
        }

    # ================= 階段 2～5：14B 集群開發與主管裁決 =================
    def execute_development_pipeline(self, plan_data: dict):
        task = plan_data["task"]
        task_id = task["task_id"]
        title = task["title"]
        contract = plan_data["contract"]
        decided_ctx = plan_data["decided_ctx"]
        proj_dir = plan_data["proj_dir"]
        test_file = plan_data["test_file"]
        golden_test = plan_data["golden_test"]
        clean_name = plan_data["clean_name"]
        desc = plan_data["desc"]
        is_project_task = task.get("is_project", False)

        start_task_time = time.time()
        task_total_tokens = 0
        lessons_prompt = self.get_lessons_context()

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeElapsedColumn(),
                console=console
            ) as progress:

                overall_task = progress.add_task(f"[bold green][{task_id}] 開發驗收[/bold green]", total=4)
                slot_1 = progress.add_task("[yellow]待命...[/yellow]", total=None)

                def make_token_cb(task_slot, emp_name: str):
                    def cb(token: str, count: int):
                        nonlocal task_total_tokens
                        task_total_tokens += 1
                        progress.update(task_slot, description=f"[cyan]{emp_name}[/cyan] ({count} tokens)")
                    return cb

                file_specs = contract.get("files", [{"filename": f"{clean_name}_module.py", "instruction": desc}])

                # 階段 2：14B 集群代碼實作
                progress.update(overall_task, description=f"[1/4] [{task_id}] 14B 集群實現模組代碼...")
                dev_pool = ["EMP-04", "EMP-06", "EMP-05"]
                generated_files = {}

                for idx, f_info in enumerate(file_specs):
                    if self.is_stop_requested():
                        self.update_task_status(task_id, "pending")
                        return

                    fname = f_info["filename"]
                    rel_file_path = f"{proj_dir}/{fname}"
                    assigned_emp_id = dev_pool[idx % len(dev_pool)]

                    prior_context = ""
                    if generated_files:
                        prior_context = "【專案已完成之檔案清單與完整介面（嚴格遵循其類別簽名）】：\n" + "\n".join(
                            [f"--- {fn} ---\n{code[:4000]}" for fn, code in generated_files.items()]
                        )

                    f_prompt = f"""請實現檔案 `{fname}` 的完整 Python 原始碼以通過 TDD 測試。
指令：{f_info['instruction']}
{prior_context}
{lessons_prompt}

【嚴格環境限制】：
1. 僅使用 Python 標準庫或專案宣告庫，嚴禁引入未安裝庫（如 cv2 等）。
2. 若調用上述已完成檔案的類別與函式，參數數量與型別必須 100% 精確匹配。
3. 直接輸出純 Python 原始碼，不含任何 Markdown 或多餘解說。"""

                    with self.employee_locks[assigned_emp_id]:
                        emp = self.staff.get_employee(assigned_emp_id)
                        try:
                            self.sync_realtime_memory()
                            f_code = emp.work(
                                f_prompt, 
                                current_task_id=task_id,
                                action_name=f"實作模組 {fname}",
                                temperature=0.1, 
                                num_ctx=decided_ctx, 
                                on_token=make_token_cb(slot_1, f"{emp.title} 實作 {fname}")
                            )
                            clean_code = f_code.replace("```python", "").replace("```", "").strip()
                        except Exception as e:
                            clean_code = f"# {fname}\npass\n"
                        finally:
                            self.sync_realtime_memory()

                    self.gateway.write_text(rel_file_path, clean_code)
                    generated_files[fname] = clean_code

                progress.advance(overall_task, 1)

                # 階段 3：TDD 驗證與主管階梯升級
                progress.update(overall_task, description=f"[2/4] [{task_id}] TDD 驗證與主管階梯升級...")
                escalation_ladder = [
                    {"tier": "Tier 1: 審查員自修 (14B)", "emp_id": "EMP-06", "ctx": max(decided_ctx, 16384), "allow_fix_test": False},
                    {"tier": "Tier 2: 研發主管重構 (32B)", "emp_id": "EMP-02", "ctx": min(decided_ctx * 2, 65536), "allow_fix_test": False},
                    {"tier": "Tier 3: 仲裁長終裁 (32B)", "emp_id": "EMP-03", "ctx": 65536, "allow_fix_test": True} # 仲裁長有權重構測試腳本
                ]

                is_success = False
                last_err_msg = ""
                escalation_tier_used = 0

                for idx_step, step in enumerate(escalation_ladder):
                    if self.is_stop_requested():
                        self.update_task_status(task_id, "pending")
                        return

                    run_res = self.sandbox.run_python_code(test_file, timeout=30.0)
                    if run_res["success"]:
                        is_success = True
                        console.print(f"[bold green]  ✔ [{task_id}] 驗證通過！[/bold green]")
                        break

                    escalation_tier_used = idx_step + 1
                    last_err_msg = run_res["stderr"]
                    parsed_err = self.parser.parse(last_err_msg)
                    console.print(f"[yellow]  ! [{task_id}] 測試未通過: {parsed_err['error_type']} - {parsed_err['error_message']}[/yellow]")
                    console.print(f"[bold magenta]  ▲ [{task_id}] 觸發升級機制 [{step['tier']}]：指派 {step['emp_id']}[/bold magenta]")

                    current_project_summary = "\n\n".join(
                        [f"=== 檔案: {fn} ===\n{code}" for fn, code in generated_files.items()]
                    )

                    test_fix_instruction = ""
                    if step["allow_fix_test"]:
                        test_fix_instruction = f"""\n【仲裁長特殊權限】：若經審查判定測試腳本 `{Path(test_file).name}` 自身的斷言存在非合理邊界要求或錯誤，您被授權同時修正該測試腳本！請同樣以 <<<FILE: {Path(test_file).name}>>> 格式輸出修正後的測試腳本。"""

                    fix_prompt = f"""專案 TDD 整合測試失敗。請重構有問題的檔案代碼以通過驗證。
【當前專案原始碼】：
{current_project_summary}

【當前 TDD 測試腳本 ({test_file})】：
{golden_test}

【報錯堆疊】：
{last_err_msg}
{test_fix_instruction}

【重構規範】：
1. 嚴禁引入外部未安裝的庫（如 cv2 等），請使用 Python 標準庫解決。
2. 檢查各檔案間的類別實例化參數（如 __init__）或演算法斷言是否合理對齊。
3. 請針對需要修復的檔案輸出完整代碼，包裹格式如下：
<<<FILE: 檔案名稱.py>>>
(完整代碼)
<<<END_FILE>>>"""

                    with self.employee_locks[step["emp_id"]]:
                        repairer = self.staff.get_employee(step["emp_id"])
                        try:
                            self.sync_realtime_memory()
                            fixed_raw = repairer.work(
                                fix_prompt, 
                                current_task_id=task_id,
                                action_name=f"仲裁重構 (Tier {escalation_tier_used})",
                                temperature=0.1, 
                                num_ctx=step["ctx"], 
                                on_token=make_token_cb(slot_1, f"{repairer.title} 裁決重構")
                            )

                            file_blocks = re.findall(r"<<<FILE:\s*(.*?)>>>(.*?)<<<END_FILE>>>", fixed_raw, re.DOTALL)
                            if file_blocks:
                                for target_fn, c_code in file_blocks:
                                    target_fn = target_fn.strip()
                                    c_code = c_code.replace("```python", "").replace("```", "").strip()
                                    if is_valid_python(c_code):
                                        if target_fn == Path(test_file).name and step["allow_fix_test"]:
                                            self.gateway.write_text(test_file, c_code)
                                            golden_test = c_code
                                            console.print(f"[bold cyan]  ⚖ [{task_id}] 仲裁長重構並修正了測試腳本: {target_fn}[/bold cyan]")
                                        else:
                                            self.gateway.write_text(f"{proj_dir}/{target_fn}", c_code)
                                            generated_files[target_fn] = c_code
                            else:
                                cand_code = fixed_raw.replace("```python", "").replace("```", "").strip()
                                if is_valid_python(cand_code):
                                    primary_file = list(generated_files.keys())[0]
                                    self.gateway.write_text(f"{proj_dir}/{primary_file}", cand_code)
                                    generated_files[primary_file] = cand_code
                        except Exception as e:
                            logger.warning(f"[{task_id}] 主管修復受阻: {e}")
                        finally:
                            self.sync_realtime_memory()

                if not is_success:
                    final_run = self.sandbox.run_python_code(test_file, timeout=30.0)
                    if final_run["success"]:
                        is_success = True
                        console.print(f"[bold green]  ✔ [{task_id}] 最終驗證通過！[/bold green]")
                    else:
                        console.print(f"[bold red]  ✘ [{task_id}] 全階梯升級結束，仍未通過驗證。最後錯誤: {final_run['stderr'][:200]}[/bold red]")

                is_first_pass = (escalation_tier_used == 0 and is_success)
                final_log = f"驗證結果: {'通過 TDD 驗證' if is_success else '全級別升級後仍未通過'}"
                progress.advance(overall_task, 1)

                # 階段 4：成果交付
                progress.update(overall_task, description=f"[3/4] [{task_id}] 交付成果至 03_delivery...")
                if is_success:
                    doc_prompt = f"""請為通過驗收的模組撰寫繁體中文說明文檔。
專案名稱：{title}
產出檔案：{list(generated_files.keys())}
原始碼概覽：
{str(list(generated_files.values()))[:1200]}

規範：說明架構與呼叫示範，輸出純 Markdown。"""

                    with self.employee_locks["EMP-07"]:
                        self.sync_realtime_memory()
                        sec_res = self.staff.get_employee("EMP-07").work(
                            f"審查安全性：\n{str(generated_files)[:1000]}", task_id, "安全審查", None, 0.1, 8192
                        )
                        self.sync_realtime_memory()

                    with self.employee_locks["EMP-09"]:
                        self.sync_realtime_memory()
                        doc_res = self.staff.get_employee("EMP-09").work(
                            doc_prompt, task_id, "撰寫技術文檔", None, 0.2, 8192
                        )
                        self.sync_realtime_memory()

                    if is_project_task or len(generated_files) > 1:
                        delivery_proj_dir = DELIVERY_ZONE / "projects" / f"{task_id}_{clean_name}"
                        delivery_proj_dir.mkdir(parents=True, exist_ok=True)
                        for fn, fcontent in generated_files.items():
                            (delivery_proj_dir / fn).write_text(fcontent, encoding="utf-8")
                        (delivery_proj_dir / "README.md").write_text(doc_res, encoding="utf-8")
                        (delivery_proj_dir / "test_suite.py").write_text(golden_test, encoding="utf-8")
                        final_log += f" | 已交付完整專案至 03_delivery/projects/{delivery_proj_dir.name}"
                    else:
                        primary_fn = list(generated_files.keys())[0]
                        delivery_filename = f"{task_id}_{primary_fn}"
                        (DELIVERY_ZONE / "source_code" / delivery_filename).write_text(list(generated_files.values())[0], encoding="utf-8")
                        (DELIVERY_ZONE / "reports" / f"{task_id}_delivery_note.md").write_text(doc_res, encoding="utf-8")
                        final_log += f" | 已交付至 03_delivery/source_code/{delivery_filename}"

                    self.vcs.commit_changes(f"feat({task_id}): Delivered to 03_delivery")
                    self.update_task_status(task_id, "completed")
                    self.append_lesson(task_id, "交付成功", f"任務 {title} 通過 TDD 驗收。")
                else:
                    fail_dir = HISTORY_ZONE / "failure_audits" / f"{task_id}_fail"
                    fail_dir.mkdir(parents=True, exist_ok=True)
                    for fn, fcontent in generated_files.items():
                        (fail_dir / fn).write_text(fcontent, encoding="utf-8")
                    (fail_dir / "failure_reason.txt").write_text(f"{last_err_msg}\n\n測試腳本：\n{golden_test}", encoding="utf-8")

                    self.vcs.commit_changes(f"chore({task_id}): Escalation failed")
                    self.update_task_status(task_id, "failed")
                    final_log += f" | 專案升級後仍未通過，現場存入 failure_audits"
                    self.append_lesson(task_id, "驗收失敗", f"任務 {task_id} 斷言未達標：{last_err_msg[:120]}")

                self.clean_task_zone([proj_dir])
                progress.advance(overall_task, 1)

                # 階段 5：秘書歸檔與 KPI
                progress.update(overall_task, description=f"[4/4] [{task_id}] 秘書歸檔與 KPI 度量...")
                self.summarizer.update_context(title, final_log, is_success)

                task_duration = time.time() - start_task_time
                self.metrics.record_task_metric(
                    task_id=task_id,
                    title=title,
                    duration=task_duration,
                    tokens_count=task_total_tokens,
                    is_success=is_success,
                    first_pass=is_first_pass,
                    escalation_level=escalation_tier_used,
                    assigned_models=["qwen2.5:32b", "qwen2.5-coder:14b", "qwen2.5:7b", "llama3.1:8b"]
                )
                progress.advance(overall_task, 1)

            console.rule(f"[bold green]任務 [{task_id}] 流水線結束[/bold green]")
        finally:
            self.sync_realtime_memory()

    # ================= 自適應准入調度迴圈 =================
    def run_queue_concurrently(self, max_concurrent_tasks: Optional[int] = None):
        console.rule("[bold green]EnterpriseDaemon 自適應硬體調度啟動[/bold green]")
        executed_count = 0

        budget_gb = self.get_hardware_budget()
        if max_concurrent_tasks is None:
            available_for_dev = max(budget_gb - MODEL_MEMORY_MAP["qwen2.5:32b"], 0.0)
            calculated_slots = int(available_for_dev // MODEL_MEMORY_MAP["qwen2.5-coder:14b"]) + 1
            max_slots = max(1, calculated_slots)
        else:
            max_slots = max_concurrent_tasks

        console.print(f"[bold cyan]⚡ 檢測硬體預算: {budget_gb:.1f} GB | 自動啟用並行任務上限: {max_slots} 槽位[/bold cyan]")

        with ThreadPoolExecutor(max_workers=max_slots) as dev_executor:
            dev_futures = []

            while True:
                if self.is_stop_requested():
                    console.print("\n[bold red]⚠️ 收到強制終止訊號，停止派工。[/bold red]\n")
                    break

                current_budget = self.get_hardware_budget()
                dev_futures = [f for f in dev_futures if not f.done()]
                next_task = self.peek_next_pending_task()
                
                if not next_task and len(dev_futures) == 0:
                    break

                if next_task:
                    current_used = self.sync_realtime_memory()
                    required_for_planning = MODEL_MEMORY_MAP["qwen2.5:32b"]

                    emp01_is_free = not self.employee_locks["EMP-01"].locked()
                    effective_used = max(current_used - (MODEL_MEMORY_MAP["qwen2.5:32b"] if not emp01_is_free else 0.0), 0.0)
                    can_plan = (len(dev_futures) < max_slots) and emp01_is_free and ((effective_used + required_for_planning) <= current_budget)

                    if can_plan:
                        console.print(f"\n[bold green]✔ 准入通過：實時負載 {current_used:.1f} GB (規劃預算 {required_for_planning:.1f} GB) <= 總預算 {current_budget:.1f} GB。啟動 [{next_task['task_id']}] 規劃！[/bold green]")
                        plan_data = self.plan_architecture_and_context(next_task)
                        fut = dev_executor.submit(self.execute_development_pipeline, plan_data)
                        dev_futures.append(fut)
                        executed_count += 1
                        continue
                    else:
                        time.sleep(1.0)
                else:
                    time.sleep(1.0)

        try:
            CONTROL_FILE.write_text(json.dumps({"stop_requested": False, "is_running": False}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        console.print(f"\n[bold green]所有任務已處理完畢，共完成 {executed_count} 個任務。排程結束。[/bold green]\n")

if __name__ == "__main__":
    import os
    PID_FILE = TASK_ZONE / "daemon.pid"
    try:
        PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
        daemon = EnterpriseDaemon()
        daemon.run_queue_concurrently()
    except Exception as e:
        console.print_exception()
        input("\n⚠️ 排程器發生嚴重異常退出，請按 Enter 鍵關閉視窗...")
    finally:
        PID_FILE.unlink(missing_ok=True)