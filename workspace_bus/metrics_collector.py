import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import json
import time
from typing import Dict, Any, List
from config import HISTORY_ZONE

class MetricsCollector:
    def __init__(self):
        self.kpi_file = HISTORY_ZONE / "performance_kpi.json"
        self.timeline_dir = HISTORY_ZONE / "timeline_logs"
        self.timeline_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_kpi_file()

    def _ensure_kpi_file(self):
        if not self.kpi_file.exists():
            default_kpi = {
                "total_tasks": 0,
                "completed_tasks": 0,
                "failed_tasks": 0,
                "first_pass_count": 0,
                "escalated_count": 0,
                "total_tokens_generated": 0,
                "total_duration_seconds": 0.0,
                "tasks_history": []
            }
            self.kpi_file.write_text(json.dumps(default_kpi, ensure_ascii=False, indent=2), encoding="utf-8")

    def record_task_metric(
        self,
        task_id: str,
        title: str,
        duration: float,
        tokens_count: int,
        is_success: bool,
        first_pass: bool,
        escalation_level: int,
        assigned_models: List[str]
    ):
        """記錄單一任務的詳細度量數據並更新全域 KPI"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        # 1. 寫入個別任務的 Timeline Log
        timeline_entry = {
            "task_id": task_id,
            "title": title,
            "timestamp": timestamp,
            "duration_seconds": round(duration, 2),
            "total_tokens": tokens_count,
            "tokens_per_second": round(tokens_count / duration, 2) if duration > 0 else 0.0,
            "success": is_success,
            "first_pass_yield": first_pass,
            "escalation_level": escalation_level,
            "models_involved": assigned_models
        }
        log_file = self.timeline_dir / f"{task_id}_timeline.json"
        log_file.write_text(json.dumps(timeline_entry, ensure_ascii=False, indent=2), encoding="utf-8")

        # 2. 更新全域 performance_kpi.json
        try:
            kpi_data = json.loads(self.kpi_file.read_text(encoding="utf-8"))
            kpi_data["total_tasks"] += 1
            if is_success:
                kpi_data["completed_tasks"] += 1
            else:
                kpi_data["failed_tasks"] += 1

            if first_pass:
                kpi_data["first_pass_count"] += 1

            if escalation_level > 0:
                kpi_data["escalated_count"] += 1

            kpi_data["total_tokens_generated"] += tokens_count
            kpi_data["total_duration_seconds"] = round(kpi_data["total_duration_seconds"] + duration, 2)
            kpi_data["tasks_history"].append({
                "task_id": task_id,
                "title": title,
                "duration": round(duration, 2),
                "tokens": tokens_count,
                "success": is_success,
                "first_pass": first_pass,
                "escalation_tier": escalation_level
            })

            self.kpi_file.write_text(json.dumps(kpi_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[警告] 更新 KPI 數據失敗: {e}")