from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = BASE_DIR / "enterprise_workspace"

# 四大專區
EMPLOYEE_ZONE = WORKSPACE_DIR / "01_staff"
TASK_ZONE = WORKSPACE_DIR / "02_tasks"
DELIVERY_ZONE = WORKSPACE_DIR / "03_delivery"
HISTORY_ZONE = WORKSPACE_DIR / "04_history"

SHARED_TOOLS_DIR = BASE_DIR / "tools" / "shared"
MAX_MEMORY_GB = 32.0
OLLAMA_API_URL = "http://localhost:11434"

# 建立核心專區目錄
for zone in [EMPLOYEE_ZONE, TASK_ZONE, DELIVERY_ZONE, HISTORY_ZONE, SHARED_TOOLS_DIR]:
    zone.mkdir(parents=True, exist_ok=True)

# 建立交付與歷史專區子目錄
(DELIVERY_ZONE / "source_code").mkdir(parents=True, exist_ok=True)
(DELIVERY_ZONE / "reports").mkdir(parents=True, exist_ok=True)
(DELIVERY_ZONE / "spreadsheets").mkdir(parents=True, exist_ok=True)
(DELIVERY_ZONE / "visual_charts").mkdir(parents=True, exist_ok=True)
(HISTORY_ZONE / "failure_audits").mkdir(parents=True, exist_ok=True)
(HISTORY_ZONE / "timeline_logs").mkdir(parents=True, exist_ok=True)