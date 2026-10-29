import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import json
import logging
import threading
from typing import Optional, List, Dict, Any
from config import EMPLOYEE_ZONE
from memory_slots.ollama_client import OllamaClient

logger = logging.getLogger("EmployeeManager")
status_lock = threading.Lock()

class Employee:
    def __init__(self, emp_id: str, name: str, role: str, title: str, model: str, system_prompt: str, manager: 'EnterpriseStaffManager'):
        self.emp_id = emp_id
        self.name = name
        self.role = role
        self.title = title
        self.model = model
        self.system_prompt = system_prompt
        self.manager = manager
        self.ollama_client = OllamaClient()

    def work(
        self,
        task_prompt: str,
        current_task_id: str,
        action_name: str,
        images: Optional[List[str]] = None,
        temperature: float = 0.1,
        num_ctx: int = 8192,
        format_json: bool = False,
        on_token: Optional[Any] = None
    ) -> str:
        self.manager.update_employee_status(self.emp_id, "working", current_task_id, action_name)
        logger.info(f"[{self.emp_id} {self.title}] 開始工作 (模型: {self.model}, Ctx: {num_ctx}, 任務: {current_task_id}, 動作: {action_name})...")
        try:
            return self.ollama_client.generate(
                model=self.model,
                prompt=task_prompt,
                system_prompt=self.system_prompt,
                images=images,
                temperature=temperature,
                num_ctx=num_ctx,
                format_json=format_json,
                on_token=on_token
            )
        finally:
            self.manager.update_employee_status(self.emp_id, "idle", "-", "待命就緒")

class EnterpriseStaffManager:
    def __init__(self):
        self.roster_file = EMPLOYEE_ZONE / "staff_roster.json"
        self.status_file = EMPLOYEE_ZONE / "employee_status.json"
        self._ensure_files()

    def _ensure_files(self):
        if not self.roster_file.exists():
            self._init_default_roster()
        if not self.status_file.exists():
            self._reset_status_file()

    def _reset_status_file(self):
        with status_lock:
            statuses = {f"EMP-{i:02d}": {"status": "idle", "task": "-", "action": "待命就緒"} for i in range(1, 13)}
            self.status_file.write_text(json.dumps(statuses, ensure_ascii=False, indent=2), encoding="utf-8")

    def _init_default_roster(self):
        default_data = {
            "hardware_budget_gb": 40.0,
            "staff": [
                {
                    "id": "EMP-01",
                    "name": "Alexander",
                    "role": "Chief Architect & Strategic Planner",
                    "title": "CEO / Architect",
                    "model": "qwen2.5:32b",
                    "system_prompt": "You are Alexander, Chief Architect. Deconstruct system architecture, design strict TDD contracts, and allocate token context."
                },
                {
                    "id": "EMP-02",
                    "name": "Marcus",
                    "role": "Senior Tech Lead & Code Refactorer",
                    "title": "Tech Lead",
                    "model": "qwen2.5-coder:32b",
                    "system_prompt": "You are Marcus, Senior Tech Lead. Resolve architectural failures and execute high-tier code refactoring."
                },
                {
                    "id": "EMP-03",
                    "name": "Valeria",
                    "role": "Chief Arbiter & Quality Gatekeeper",
                    "title": "Chief Arbiter",
                    "model": "qwen2.5-coder:32b",
                    "system_prompt": "You are Valeria, Chief Arbiter. You hold the ultimate authority to rewrite broken implementations and enforce project completion."
                },
                {
                    "id": "EMP-04",
                    "name": "Ethan",
                    "role": "Core Fullstack Engineer",
                    "title": "Fullstack Dev",
                    "model": "qwen2.5-coder:14b",
                    "system_prompt": "You are Ethan, Core Fullstack Engineer. Write robust, bug-free Python implementations satisfying TDD test suites."
                },
                {
                    "id": "EMP-05",
                    "name": "David",
                    "role": "Backend Systems & Service Engineer",
                    "title": "Backend Dev",
                    "model": "qwen2.5-coder:14b",
                    "system_prompt": "You are David, Backend Specialist. Build scalable services, event dispatchers, and clean data contracts."
                },
                {
                    "id": "EMP-06",
                    "name": "Elena",
                    "role": "Code Reviewer & Tier-1 Repairer",
                    "title": "Code Reviewer",
                    "model": "qwen2.5-coder:14b",
                    "system_prompt": "You are Elena, Code Reviewer. Audit stack traces, diagnose syntax and assertion flaws, and fix modules precisely."
                },
                {
                    "id": "EMP-07",
                    "name": "Victor",
                    "role": "Security & Code Integrity Auditor",
                    "title": "Security Auditor",
                    "model": "qwen2.5:7b",
                    "system_prompt": "You are Victor, Security Auditor. Check code against vulnerabilities, injection risks, and verify security integrity."
                },
                {
                    "id": "EMP-08",
                    "name": "Sarah",
                    "role": "Vision & Multimodal Analyst",
                    "title": "Vision Analyst",
                    "model": "llava:latest",
                    "system_prompt": "You are Sarah, Multimodal Vision Analyst. Extract data trends, coordinates, and specifications from images."
                },
                {
                    "id": "EMP-09",
                    "name": "Chloe",
                    "role": "Technical Writer & Delivery Note Author",
                    "title": "Tech Writer",
                    "model": "llama3.1:8b",
                    "system_prompt": "You are Chloe, Technical Writer. Produce crystal-clear Traditional Chinese documentation and caller examples."
                },
                {
                    "id": "EMP-10",
                    "name": "Lucas",
                    "role": "Executive Secretary & Workflow Archivist",
                    "title": "Executive Secretary",
                    "model": "llama3.1:8b",
                    "system_prompt": "You are Lucas, Executive Secretary. Maintain continuous project logs, track metrics, and summarize execution context."
                },
                {
                    "id": "EMP-11",
                    "name": "Grace",
                    "role": "Data Analyst & Table Validator",
                    "title": "Data Analyst",
                    "model": "qwen2.5:7b",
                    "system_prompt": "You are Grace, Data Analyst. Process tabular schemas, clean dataset anomalies, and verify data transformations."
                },
                {
                    "id": "EMP-12",
                    "name": "Noah",
                    "role": "Tool Specialist & Environment Integrator",
                    "title": "Tool Specialist",
                    "model": "qwen2.5:7b",
                    "system_prompt": "You are Noah, Tool Specialist. Maintain external integrations, registry functions, and local system utilities."
                }
            ]
        }
        self.roster_file.write_text(json.dumps(default_data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._reset_status_file()
        logger.info("已成功重置 12 位虛擬專員預設名冊與待命狀態")

    def get_employee(self, emp_id: str) -> Employee:
        try:
            data = json.loads(self.roster_file.read_text(encoding="utf-8"))
            for s in data.get("staff", []):
                if s["id"] == emp_id:
                    return Employee(
                        emp_id=s["id"],
                        name=s["name"],
                        role=s["role"],
                        title=s["title"],
                        model=s["model"],
                        system_prompt=s["system_prompt"],
                        manager=self
                    )
        except Exception as e:
            logger.warning(f"讀取名冊異常，使用預設配置: {e}")

        return Employee(
            emp_id=emp_id,
            name="Agent",
            role="Specialist",
            title="Engineer",
            model="qwen2.5-coder:14b",
            system_prompt="You are a professional engineer.",
            manager=self
        )

    def update_employee_status(self, emp_id: str, status: str, task: str = "-", action: str = "待命就緒"):
        with status_lock:
            try:
                statuses = {}
                if self.status_file.exists():
                    try:
                        statuses = json.loads(self.status_file.read_text(encoding="utf-8"))
                    except Exception:
                        statuses = {}
                statuses[emp_id] = {
                    "status": status,
                    "task": task,
                    "action": action
                }
                self.status_file.write_text(json.dumps(statuses, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass