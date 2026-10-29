import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import json
import shutil
import time
import subprocess
import os
import signal
import re
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import uvicorn

from config import WORKSPACE_DIR, TASK_ZONE, DELIVERY_ZONE, HISTORY_ZONE, EMPLOYEE_ZONE
import config

app = FastAPI(title="Local Autonomous AI Enterprise")
UPLOAD_DIR = WORKSPACE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

CONTROL_FILE = TASK_ZONE / "daemon_control.json"
MEM_USAGE_FILE = TASK_ZONE / "memory_usage.json"
PID_FILE = TASK_ZONE / "daemon.pid"

(DELIVERY_ZONE / "source_code").mkdir(parents=True, exist_ok=True)
(DELIVERY_ZONE / "reports").mkdir(parents=True, exist_ok=True)
(DELIVERY_ZONE / "spreadsheets").mkdir(parents=True, exist_ok=True)
(DELIVERY_ZONE / "projects").mkdir(parents=True, exist_ok=True)

STAFF_MODEL_MEM = {
    "EMP-01": 20.0, "EMP-02": 20.0, "EMP-03": 20.0,
    "EMP-04": 9.5, "EMP-05": 9.5, "EMP-06": 9.5,
    "EMP-07": 5.5, "EMP-08": 7.0, "EMP-09": 6.0,
    "EMP-10": 6.0, "EMP-11": 5.5, "EMP-12": 5.5
}

def get_daemon_pid() -> Optional[int]:
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            return None
    return None

def is_pid_running(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

def calculate_next_task_id(tasks: list) -> str:
    max_num = 0
    for t in tasks:
        tid = t.get("task_id", "")
        match = re.search(r"TASK-(\d+)", tid)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"TASK-{(max_num + 1):03d}"

@app.get("/api/state")
def get_state():
    pid = get_daemon_pid()
    is_daemon_running = (pid is not None and is_pid_running(pid))

    staff_data = []
    roster_file = EMPLOYEE_ZONE / "staff_roster.json"
    status_file = EMPLOYEE_ZONE / "employee_status.json"
    dynamic_status = {}
    if status_file.exists():
        try:
            dynamic_status = json.loads(status_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    current_mem = 40.0
    used_mem = 0.0

    if roster_file.exists():
        try:
            raw_staff = json.loads(roster_file.read_text(encoding="utf-8")).get("staff", [])
            r_data = json.loads(roster_file.read_text(encoding="utf-8"))
            current_mem = float(r_data.get("hardware_budget_gb", getattr(config, "MAX_MEMORY_GB", 40.0)))

            for s in raw_staff:
                st = dynamic_status.get(s["id"], {"status": "idle", "task": "-", "action": "待命就緒"})
                actual_status = st.get("status", "idle") if is_daemon_running else "idle"
                actual_task = st.get("task", "-") if is_daemon_running else "-"
                actual_action = st.get("action", "") if is_daemon_running else "待命就緒"

                if actual_status == "working":
                    used_mem += STAFF_MODEL_MEM.get(s["id"], 8.0)

                staff_data.append({
                    **s,
                    "work_status": actual_status,
                    "current_task": actual_task,
                    "action_detail": actual_action
                })
        except Exception:
            pass

    free_mem = max(current_mem - used_mem, 0.0)

    tasks = []
    backlog_file = TASK_ZONE / "task_backlog.json"
    if backlog_file.exists():
        try:
            tasks = json.loads(backlog_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    next_task_id = calculate_next_task_id(tasks)

    delivery_items = []
    proj_dir = DELIVERY_ZONE / "projects"
    if proj_dir.exists():
        for p in proj_dir.iterdir():
            if p.is_dir():
                sub_files = [str(f.relative_to(proj_dir)).replace("\\", "/") for f in p.rglob("*") if f.is_file() and f.name != ".gitkeep"]
                delivery_items.append({
                    "type": "project",
                    "title": p.name,
                    "files": sub_files
                })

    for f in (DELIVERY_ZONE / "source_code").glob("*.py"):
        if f.name != ".gitkeep":
            delivery_items.append({"type": "source_code", "title": f.name, "path": f"source_code/{f.name}"})

    for f in (DELIVERY_ZONE / "reports").glob("*.md"):
        if f.name != ".gitkeep":
            delivery_items.append({"type": "report", "title": f.name, "path": f"reports/{f.name}"})

    for f in (DELIVERY_ZONE / "spreadsheets").glob("*.*"):
        if f.name != ".gitkeep":
            delivery_items.append({"type": "spreadsheet", "title": f.name, "path": f"spreadsheets/{f.name}"})

    lessons = []
    lessons_file = HISTORY_ZONE / "lessons_learned.json"
    if lessons_file.exists():
        try:
            lessons = json.loads(lessons_file.read_text(encoding="utf-8"))[-6:]
        except Exception:
            pass

    return {
        "max_memory_gb": current_mem,
        "used_memory_gb": round(used_mem, 1),
        "free_memory_gb": round(free_mem, 1),
        "is_daemon_running": is_daemon_running,
        "staff": staff_data,
        "tasks": tasks,
        "next_task_id": next_task_id,
        "delivery_items": delivery_items,
        "lessons": lessons
    }

@app.post("/api/control/stop")
def stop_daemon():
    try:
        CONTROL_FILE.write_text(json.dumps({"stop_requested": True, "is_running": False}, ensure_ascii=False, indent=2), encoding="utf-8")

        pid = get_daemon_pid()
        if pid and is_pid_running(pid):
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, signal.SIGKILL)
        
        if PID_FILE.exists():
            PID_FILE.unlink(missing_ok=True)
        if MEM_USAGE_FILE.exists():
            MEM_USAGE_FILE.write_text(json.dumps({"used_memory_gb": 0.0}), encoding="utf-8")

        backlog_file = TASK_ZONE / "task_backlog.json"
        if backlog_file.exists():
            tasks = json.loads(backlog_file.read_text(encoding="utf-8"))
            for t in tasks:
                if t.get("status") == "processing":
                    t["status"] = "pending"
            backlog_file.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")

        status_file = EMPLOYEE_ZONE / "employee_status.json"
        statuses = {f"EMP-{i:02d}": {"status": "idle", "task": "-", "action": "待命就緒"} for i in range(1, 13)}
        status_file.write_text(json.dumps(statuses, ensure_ascii=False, indent=2), encoding="utf-8")

        return {"status": "ok", "message": "已成功強制終止背景排程 / Pipeline stopped successfully!"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/api/control/resume")
def resume_daemon():
    try:
        pid = get_daemon_pid()
        if pid and is_pid_running(pid):
            return {"status": "ok", "message": f"排程器已在執行中 / Daemon already running (PID: {pid})!"}

        if PID_FILE.exists():
            PID_FILE.unlink(missing_ok=True)

        CONTROL_FILE.write_text(json.dumps({"stop_requested": False, "is_running": True}, ensure_ascii=False, indent=2), encoding="utf-8")
        
        py_exe = sys.executable
        daemon_script = str((BASE_DIR / "daemon.py").resolve())
        
        if sys.platform == "win32":
            proc = subprocess.Popen(
                ["cmd.exe", "/k", py_exe, daemon_script],
                cwd=str(BASE_DIR),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        else:
            proc = subprocess.Popen(
                [py_exe, daemon_script],
                cwd=str(BASE_DIR)
            )
        
        return {"status": "ok", "message": "排程器已啟動 / Daemon launched successfully!"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/api/tasks/retry_failed")
def api_retry_failed_tasks():
    backlog_file = TASK_ZONE / "task_backlog.json"
    if not backlog_file.exists():
        return {"status": "ok", "message": "佇列為空 / Backlog is empty"}

    try:
        tasks = json.loads(backlog_file.read_text(encoding="utf-8"))
    except Exception:
        tasks = []

    retry_list = [t for t in tasks if t.get("status") in ["failed", "pending", "processing"]]
    if not retry_list:
        return {"status": "ok", "message": "無失敗任務需要重試 / No failed tasks to retry"}

    for idx, t in enumerate(retry_list, start=1):
        old_id = t.get("task_id")
        new_id = f"TASK-{idx:03d}"
        t["task_id"] = new_id
        t["status"] = "pending"
        if t.get("image_path") and old_id:
            old_img = Path(t["image_path"])
            if old_img.exists() and old_id in old_img.name:
                new_img_name = old_img.name.replace(old_id, new_id)
                new_img_path = old_img.parent / new_img_name
                try:
                    old_img.rename(new_img_path)
                    t["image_path"] = str(new_img_path)
                except Exception:
                    pass

    backlog_file.write_text(json.dumps(retry_list, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # 清理殘留暫存資料夾
    preserved_task_files = {
        "task_backlog.json", "active_context.md", "daemon_control.json",
        "memory_usage.json", ".gitkeep"
    }
    for item in TASK_ZONE.iterdir():
        if item.name not in preserved_task_files:
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except Exception:
                pass

    return {"status": "ok", "message": f"已清理完成任務，共 {len(retry_list)} 個失敗/待處理任務重整為 TASK-001 並就緒！"}

@app.post("/api/config/memory")
def update_memory(memory_gb: float = Form(...)):
    config.MAX_MEMORY_GB = float(memory_gb)
    roster_file = EMPLOYEE_ZONE / "staff_roster.json"
    if roster_file.exists():
        try:
            data = json.loads(roster_file.read_text(encoding="utf-8"))
            data["hardware_budget_gb"] = float(memory_gb)
            roster_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return {"status": "ok", "new_memory_gb": config.MAX_MEMORY_GB}

@app.post("/api/tasks/create")
async def create_task(
    title: str = Form(...),
    description: str = Form(...),
    task_id: Optional[str] = Form(None),
    is_project: bool = Form(False),
    file: Optional[UploadFile] = File(None)
):
    backlog_file = TASK_ZONE / "task_backlog.json"
    tasks = []
    if backlog_file.exists():
        try:
            tasks = json.loads(backlog_file.read_text(encoding="utf-8"))
        except Exception:
            tasks = []

    if not task_id or not task_id.strip():
        task_id = calculate_next_task_id(tasks)

    saved_file_path = None
    if file and file.filename:
        dest = UPLOAD_DIR / f"{task_id}_{file.filename}"
        with open(dest, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_file_path = str(dest)

    final_desc = description
    if saved_file_path and (saved_file_path.endswith(".xlsx") or saved_file_path.endswith(".csv")):
        from workspace_bus.excel_sync import ExcelSync
        sync = ExcelSync()
        summary = sync.extract_excel_summary(saved_file_path)
        final_desc += f"\n\n【Excel 試算表結構資訊】：\n{json.dumps(summary, ensure_ascii=False, indent=2)}"

    new_task = {
        "task_id": task_id.strip(),
        "title": title.strip(),
        "description": final_desc,
        "is_project": is_project,
        "status": "pending"
    }
    if saved_file_path and any(saved_file_path.endswith(ext) for ext in [".png", ".jpg", ".jpeg"]):
        new_task["image_path"] = saved_file_path

    tasks.append(new_task)
    backlog_file.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "ok", "task_id": task_id}

@app.get("/api/download/{zone}/{subpath:path}")
def download_file(zone: str, subpath: str):
    allowed_zones = {
        "source_code": DELIVERY_ZONE / "source_code",
        "reports": DELIVERY_ZONE / "reports",
        "spreadsheets": DELIVERY_ZONE / "spreadsheets",
        "projects": DELIVERY_ZONE / "projects"
    }
    target_dir = allowed_zones.get(zone)
    if not target_dir:
        return JSONResponse({"error": "非法區域 / Invalid Zone"}, status_code=400)
    file_path = (target_dir / subpath).resolve()
    if not file_path.exists() or not str(file_path).startswith(str(target_dir.resolve())):
        return JSONResponse({"error": "檔案不存在或存取受限 / File not found or access denied"}, status_code=404)
    return FileResponse(file_path, filename=file_path.name)

@app.get("/", response_class=HTMLResponse)
def index_page():
    return """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Local Autonomous AI Enterprise Dashboard</title>
    <style>
        :root {
            --bg: #0b1120;
            --panel: #131d33;
            --panel-border: #1e293b;
            --accent: #38bdf8;
            --accent-dim: #0284c7;
            --text: #f8fafc;
            --dim: #94a3b8;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            padding: 12px 18px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
            background: var(--bg);
            color: var(--text);
            height: 100vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 10px;
            border-bottom: 1px solid var(--panel-border);
            flex-shrink: 0;
        }
        .header-left { display: flex; align-items: center; gap: 12px; }
        .header-title { font-size: 18px; font-weight: bold; margin: 0; color: #fff; display: flex; align-items: center; gap: 8px; }
        .header-right { display: flex; align-items: center; gap: 10px; }

        .status-pill { padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: bold; background: #334155; }
        .mem-indicator { display: flex; align-items: center; gap: 6px; background: #0f172a; padding: 5px 10px; border-radius: 6px; border: 1px solid var(--panel-border); font-size: 11px; }

        .btn-ctrl { width: auto; margin-top: 0; padding: 6px 12px; font-size: 12px; border-radius: 6px; font-weight: bold; cursor: pointer; border: none; color: white; transition: 0.15s; }
        .btn-stop { background: #dc2626; }
        .btn-stop:hover { background: #b91c1c; }
        .btn-resume { background: #16a34a; }
        .btn-resume:hover { background: #15803d; }
        .btn-primary { background: #0284c7; }
        .btn-primary:hover { background: #0369a1; }
        .btn-lang { background: #334155; border: 1px solid #475569; }
        .btn-lang:hover { background: #475569; }

        .main-layout {
            display: grid;
            grid-template-columns: 340px 1fr;
            gap: 14px;
            flex: 1;
            margin-top: 10px;
            min-height: 0;
        }
        .left-col { display: flex; flex-direction: column; gap: 10px; min-height: 0; }
        .right-col { display: flex; flex-direction: column; gap: 10px; min-height: 0; }

        .card {
            background: var(--panel);
            border-radius: 8px;
            padding: 12px 14px;
            border: 1px solid var(--panel-border);
            display: flex;
            flex-direction: column;
        }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
        .card-title { font-size: 13px; font-weight: bold; color: var(--accent); margin: 0; display: flex; align-items: center; gap: 6px; }

        label { display: block; margin: 6px 0 2px; font-size: 11px; color: var(--dim); }
        input[type="text"], input[type="number"], textarea, input[type="file"] {
            width: 100%;
            background: #0b1120;
            border: 1px solid #334155;
            color: #fff;
            padding: 6px 8px;
            border-radius: 5px;
            font-size: 12px;
        }
        input:focus, textarea:focus { outline: 1px solid var(--accent); }

        .staff-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 6px;
        }
        .staff-card {
            background: #0b1120;
            padding: 6px 8px;
            border-radius: 5px;
            border-left: 3px solid #059669;
            transition: all 0.2s;
        }
        .staff-card.working {
            border-left-color: #f59e0b;
            background: #172136;
            box-shadow: 0 0 6px rgba(245, 158, 11, 0.2);
        }
        .staff-top { display: flex; justify-content: space-between; align-items: center; font-size: 11px; }
        .status-badge { font-size: 9px; padding: 1px 4px; border-radius: 3px; font-weight: bold; }
        .badge-idle { background: #064e3b; color: #34d399; }
        .badge-working { background: #78350f; color: #fbbf24; animation: pulse 1.2s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }

        .pagination-bar {
            display: flex;
            justify-content: flex-end;
            align-items: center;
            gap: 8px;
            font-size: 11px;
            color: var(--dim);
        }
        .page-btn {
            background: #1e293b;
            border: 1px solid #334155;
            color: #fff;
            padding: 2px 7px;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
        }
        .page-btn:disabled { opacity: 0.4; cursor: not-allowed; }
        .page-btn:not(:disabled):hover { background: #334155; }

        .list-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 6px;
            min-height: 0;
            overflow-y: auto;
        }
        .task-item {
            padding: 6px 10px;
            background: #0b1120;
            border-radius: 5px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border: 1px solid #1e293b;
        }
        .task-left { display: flex; flex-direction: column; gap: 2px; }
        .task-title { font-size: 12px; font-weight: bold; color: #fff; }
        .task-desc { font-size: 10px; color: var(--dim); }

        .tag { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: bold; }
        .tag-pending { background: #475569; color: #cbd5e1; }
        .tag-processing { background: #f59e0b; color: #000; animation: pulse 1.2s infinite; }
        .tag-completed { background: #10b981; color: #fff; }
        .tag-failed { background: #ef4444; color: #fff; }

        .delivery-item {
            padding: 6px 10px;
            background: #0b1120;
            border-radius: 5px;
            border: 1px solid #1e293b;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 11px;
        }
        .file-link {
            color: #38bdf8;
            text-decoration: none;
            font-size: 11px;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }
        .file-link:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <header>
        <div class="header-left">
            <h1 class="header-title" id="txt_app_title">🏢 Local Autonomous AI Enterprise</h1>
            <span id="daemon_status_pill" class="status-pill">Loading...</span>
        </div>
        <div class="header-right">
            <button onclick="toggleLanguage()" class="btn-ctrl btn-lang" id="btn_lang_toggle">🌐 EN / 中文</button>
            <button onclick="retryFailedTasks()" class="btn-ctrl" style="background:#d97706;" id="btn_retry">🔄 重試失敗任務</button>
            <div class="mem-indicator">
                <span id="txt_mem_label">記憶體:</span>
                <span id="mem_used_text" style="color:#fbbf24; font-weight:bold;">0.0 GB</span>
                <span style="color:var(--dim)">/</span>
                <span id="mem_total_text" style="color:#38bdf8; font-weight:bold;">40.0 GB</span>
                <span id="mem_free_text" style="color:#34d399; font-size:10px;">(空閒: 40.0 GB)</span>
            </div>
            <button onclick="resumeDaemon()" class="btn-ctrl btn-resume" id="btn_resume">▶ 繼續</button>
            <button onclick="stopDaemon()" class="btn-ctrl btn-stop" id="btn_stop">🚨 強制終止</button>
            <div style="width: 1px; height: 18px; background: #334155;"></div>
            <input type="number" id="memory_input" style="width: 55px; padding: 4px;" step="1" min="8" max="128">
            <button onclick="saveMemory()" class="btn-ctrl btn-primary" style="padding: 4px 8px;" id="btn_save_mem">配額設定</button>
        </div>
    </header>

    <div class="main-layout">
        <div class="left-col">
            <div class="card" style="flex: 1.4;">
                <div class="card-header">
                    <h2 class="card-title" id="txt_dispatch_title">📝 派發研發任務</h2>
                </div>
                <div style="display:flex; gap: 8px;">
                    <div style="flex:1;">
                        <label id="lbl_task_id">任務編號 (預設最新+1)</label>
                        <input type="text" id="t_id" placeholder="...">
                    </div>
                    <div style="flex:2;">
                        <label id="lbl_task_title">任務標題</label>
                        <input type="text" id="t_title" placeholder="如：金流結算模組">
                    </div>
                </div>
                <label id="lbl_task_desc">詳細需求與演算法規則</label>
                <textarea id="t_desc" style="flex:1; resize:none;" placeholder="請詳細說明功能規格..."></textarea>
                <div style="margin: 6px 0; display:flex; justify-content:space-between; align-items:center;">
                    <label style="display:inline-flex; align-items:center; gap: 4px; margin:0; cursor:pointer;" id="lbl_multifile">
                        <input type="checkbox" id="t_proj" style="width:auto;"> 多檔案專案 (Multi-File)
                    </label>
                    <input type="file" id="t_file" style="width:170px; padding: 2px;" accept=".png,.jpg,.jpeg,.xlsx,.xls,.csv">
                </div>
                <button onclick="submitTask()" class="btn-ctrl btn-primary" style="width:100%; padding: 7px;" id="btn_submit_task">派發至任務佇列</button>
            </div>

            <div class="card" style="flex: 1;">
                <div class="card-header">
                    <h2 class="card-title" id="txt_lessons_title">🧠 經驗避坑指南</h2>
                </div>
                <div id="lessons_box" class="list-container" style="font-size: 11px; color: var(--dim);">
                    載入中...
                </div>
            </div>
        </div>

        <div class="right-col">
            <div class="card" style="flex-shrink: 0;">
                <div class="card-header" style="margin-bottom: 6px;">
                    <h2 class="card-title" id="txt_staff_title">👥 虛擬員工即時調度狀態</h2>
                    <div class="pagination-bar">
                        <button class="page-btn" id="staff_prev_btn" onclick="prevStaffPage()">◀</button>
                        <span id="staff_page_info">1 / 1</span>
                        <button class="page-btn" id="staff_next_btn" onclick="nextStaffPage()">▶</button>
                    </div>
                </div>
                <div class="staff-grid" id="staff_box"></div>
            </div>

            <div class="card" style="flex: 1; min-height: 0;">
                <div class="card-header">
                    <h2 class="card-title" id="txt_backlog_title">📋 任務流水線佇列 (Task Backlog)</h2>
                    <div class="pagination-bar">
                        <button class="page-btn" id="task_prev_btn" onclick="prevTaskPage()">◀</button>
                        <span id="task_page_info">1 / 1</span>
                        <button class="page-btn" id="task_next_btn" onclick="nextTaskPage()">▶</button>
                    </div>
                </div>
                <div class="list-container" id="tasks_box"></div>
            </div>

            <div class="card" style="flex: 1; min-height: 0;">
                <div class="card-header">
                    <h2 class="card-title" id="txt_delivery_title">📦 03_delivery 正式交付成果</h2>
                    <div class="pagination-bar">
                        <button class="page-btn" id="deliv_prev_btn" onclick="prevDelivPage()">◀</button>
                        <span id="deliv_page_info">1 / 1</span>
                        <button class="page-btn" id="deliv_next_btn" onclick="nextDelivPage()">▶</button>
                    </div>
                </div>
                <div class="list-container" id="deliv_box"></div>
            </div>
        </div>
    </div>

    <script>
        const I18N = {
            zh: {
                app_title: "🏢 Local Autonomous AI Enterprise",
                mem_label: "記憶體:",
                free: "空閒",
                resume: "▶ 繼續",
                stop: "🚨 強制終止",
                retry: "🔄 重試失敗任務",
                save_mem: "配額設定",
                dispatch_title: "📝 派發研發任務",
                lbl_task_id: "任務編號 (預設最新+1)",
                lbl_task_title: "任務標題",
                ph_title: "如：金流結算模組",
                lbl_task_desc: "詳細需求與演算法規則",
                ph_desc: "請詳細說明功能規格、演算法或清洗規則...",
                lbl_multifile: "多檔案專案 (Multi-File)",
                btn_submit_task: "派發至任務佇列",
                lessons_title: "🧠 經驗避坑指南",
                staff_title: "👥 虛擬員工即時調度狀態",
                backlog_title: "📋 任務流水線佇列 (Task Backlog)",
                delivery_title: "📦 03_delivery 正式交付成果",
                idle: "待命",
                working: "工作中",
                status_running: "● 運作中",
                status_stopped: "○ 已停止",
                download_btn: "下載檔案 ⬇",
                proj_prefix: "📦 完整專案:",
                no_staff: "尚無員工資料",
                no_tasks: "佇列中無任務",
                no_delivery: "目前尚無正式交付產物",
                no_lessons: "暫無歷史經驗",
                confirm_stop: "確定要強制終止排程運作嗎？未完成的任務將重置回 pending。",
                confirm_retry: "確定要清理已完成任務，並將失敗任務序號重新編排為 TASK-001 重試嗎？",
                alert_submit_empty: "請填寫任務標題與需求描述",
                alert_submit_ok: "任務已成功加入排程隊列！",
                alert_mem_saved: "記憶體預算已更新為 "
            },
            en: {
                app_title: "🏢 Local Autonomous AI Enterprise",
                mem_label: "Memory:",
                free: "Free",
                resume: "▶ Resume",
                stop: "🚨 Terminate",
                retry: "🔄 Retry Failed Tasks",
                save_mem: "Set Quota",
                dispatch_title: "📝 Dispatch R&D Task",
                lbl_task_id: "Task ID (Next Sequential)",
                lbl_task_title: "Task Title",
                ph_title: "e.g., Payment Settlement Module",
                lbl_task_desc: "Detailed Requirements & Rules",
                ph_desc: "Specify functional requirements, algorithms, or ETL rules...",
                lbl_multifile: "Multi-File Project",
                btn_submit_task: "Dispatch to Backlog",
                lessons_title: "🧠 Lessons Learned Repository",
                staff_title: "👥 Virtual Staff Telemetry",
                backlog_title: "📋 Task Backlog Pipeline",
                delivery_title: "📦 03_delivery Production Deliverables",
                idle: "Idle",
                working: "Active",
                status_running: "● Running",
                status_stopped: "○ Stopped",
                download_btn: "Download ⬇",
                proj_prefix: "📦 Project:",
                no_staff: "No staff available",
                no_tasks: "No tasks in backlog",
                no_delivery: "No production deliverables available",
                no_lessons: "No lessons recorded yet",
                confirm_stop: "Are you sure you want to stop the scheduler? Incomplete tasks will be safely reset to pending.",
                confirm_retry: "Are you sure you want to clean completed tasks and reset failed tasks sequentially from TASK-001 to retry?",
                alert_submit_empty: "Please provide both task title and requirements description.",
                alert_submit_ok: "Task successfully submitted to backlog queue!",
                alert_mem_saved: "Memory hardware budget updated to "
            }
        };

        let currentLang = localStorage.getItem("ai_enterprise_lang") || "zh";

        function applyLanguage() {
            const t = I18N[currentLang];
            document.getElementById("txt_app_title").innerText = t.app_title;
            document.getElementById("txt_mem_label").innerText = t.mem_label;
            document.getElementById("btn_resume").innerText = t.resume;
            document.getElementById("btn_stop").innerText = t.stop;
            document.getElementById("btn_retry").innerText = t.retry;
            document.getElementById("btn_save_mem").innerText = t.save_mem;
            document.getElementById("txt_dispatch_title").innerText = t.dispatch_title;
            document.getElementById("lbl_task_id").innerText = t.lbl_task_id;
            document.getElementById("lbl_task_title").innerText = t.lbl_task_title;
            document.getElementById("t_title").placeholder = t.ph_title;
            document.getElementById("lbl_task_desc").innerText = t.lbl_task_desc;
            document.getElementById("t_desc").placeholder = t.ph_desc;
            document.getElementById("lbl_multifile").childNodes[2].textContent = " " + t.lbl_multifile;
            document.getElementById("btn_submit_task").innerText = t.btn_submit_task;
            document.getElementById("txt_lessons_title").innerText = t.lessons_title;
            document.getElementById("txt_staff_title").innerText = t.staff_title;
            document.getElementById("txt_backlog_title").innerText = t.backlog_title;
            document.getElementById("txt_delivery_title").innerText = t.delivery_title;
            document.getElementById("btn_lang_toggle").innerText = currentLang === "zh" ? "🌐 English" : "🌐 繁體中文";
            localStorage.setItem("ai_enterprise_lang", currentLang);
        }

        function toggleLanguage() {
            currentLang = currentLang === "zh" ? "en" : "zh";
            applyLanguage();
            fetchState();
        }

        let allStaff = [];
        let staffPage = 1;
        const staffPageSize = 6;

        let allTasks = [];
        let taskPage = 1;
        const taskPageSize = 4;

        let allDeliveryItems = [];
        let delivPage = 1;
        const delivPageSize = 4;

        let isDaemonRunningCache = false;
        let lastServerTaskId = "";
        let userHasEditedId = false;

        document.getElementById('t_id').addEventListener('input', () => {
            userHasEditedId = true;
        });

        function renderStaff() {
            const t = I18N[currentLang];
            const container = document.getElementById('staff_box');
            if (!allStaff.length) {
                container.innerHTML = `<div style="color:var(--dim); font-size:11px;">${t.no_staff}</div>`;
                document.getElementById('staff_page_info').innerText = '1 / 1';
                document.getElementById('staff_prev_btn').disabled = true;
                document.getElementById('staff_next_btn').disabled = true;
                return;
            }

            const totalPages = Math.ceil(allStaff.length / staffPageSize) || 1;
            if (staffPage > totalPages) staffPage = totalPages;
            if (staffPage < 1) staffPage = 1;

            document.getElementById('staff_page_info').innerText = `${staffPage} / ${totalPages}`;
            document.getElementById('staff_prev_btn').disabled = (staffPage === 1);
            document.getElementById('staff_next_btn').disabled = (staffPage === totalPages);

            const start = (staffPage - 1) * staffPageSize;
            const slice = allStaff.slice(start, start + staffPageSize);

            container.innerHTML = slice.map(s => {
                const isWorking = (s.work_status === 'working' && isDaemonRunningCache);
                return `
                    <div class="staff-card ${isWorking ? 'working' : ''}">
                        <div class="staff-top">
                            <strong>${s.id}</strong>
                            <span class="status-badge ${isWorking ? 'badge-working' : 'badge-idle'}">
                                ${isWorking ? t.working : t.idle}
                            </span>
                        </div>
                        <div style="font-size:10px; font-weight:bold; margin-top:1px;">${s.title}</div>
                        ${isWorking ? `
                            <div style="font-size:9px; color:#fbbf24; font-weight:bold; margin-top:2px;">
                                ⚡ [${s.current_task}] ${s.action_detail}
                            </div>
                        ` : `
                            <div style="font-size:9px; color:#64748b; margin-top:2px;">${s.role}</div>
                        `}
                    </div>
                `;
            }).join('');
        }

        function prevStaffPage() { if (staffPage > 1) { staffPage--; renderStaff(); } }
        function nextStaffPage() { const total = Math.ceil(allStaff.length / staffPageSize); if (staffPage < total) { staffPage++; renderStaff(); } }

        function renderTasks() {
            const t = I18N[currentLang];
            const container = document.getElementById('tasks_box');
            if (!allTasks.length) {
                container.innerHTML = `<div style="color:var(--dim); font-size:11px;">${t.no_tasks}</div>`;
                document.getElementById('task_page_info').innerText = '1 / 1';
                document.getElementById('task_prev_btn').disabled = true;
                document.getElementById('task_next_btn').disabled = true;
                return;
            }

            const totalPages = Math.ceil(allTasks.length / taskPageSize) || 1;
            if (taskPage > totalPages) taskPage = totalPages;
            if (taskPage < 1) taskPage = 1;

            document.getElementById('task_page_info').innerText = `${taskPage} / ${totalPages}`;
            document.getElementById('task_prev_btn').disabled = (taskPage === 1);
            document.getElementById('task_next_btn').disabled = (taskPage === totalPages);

            const start = (taskPage - 1) * taskPageSize;
            const slice = allTasks.slice(start, start + taskPageSize);

            container.innerHTML = slice.map(item => `
                <div class="task-item">
                    <div class="task-left">
                        <span class="task-title">[${item.task_id}] ${item.title}</span>
                        <span class="task-desc">${item.description.substring(0, 75)}...</span>
                    </div>
                    <span class="tag tag-${item.status}">${item.status}</span>
                </div>
            `).join('');
        }

        function prevTaskPage() { if (taskPage > 1) { taskPage--; renderTasks(); } }
        function nextTaskPage() { const total = Math.ceil(allTasks.length / taskPageSize); if (taskPage < total) { taskPage++; renderTasks(); } }

        function renderDelivery() {
            const t = I18N[currentLang];
            const container = document.getElementById('deliv_box');
            if (!allDeliveryItems.length) {
                container.innerHTML = `<div style="color:var(--dim); font-size:11px;">${t.no_delivery}</div>`;
                document.getElementById('deliv_page_info').innerText = '1 / 1';
                document.getElementById('deliv_prev_btn').disabled = true;
                document.getElementById('deliv_next_btn').disabled = true;
                return;
            }

            const totalPages = Math.ceil(allDeliveryItems.length / delivPageSize) || 1;
            if (delivPage > totalPages) delivPage = totalPages;
            if (delivPage < 1) delivPage = 1;

            document.getElementById('deliv_page_info').innerText = `${delivPage} / ${totalPages}`;
            document.getElementById('deliv_prev_btn').disabled = (delivPage === 1);
            document.getElementById('deliv_next_btn').disabled = (delivPage === totalPages);

            const start = (delivPage - 1) * delivPageSize;
            const slice = allDeliveryItems.slice(start, start + delivPageSize);

            container.innerHTML = slice.map(item => {
                if (item.type === 'project') {
                    return `
                        <div class="delivery-item" style="flex-direction:column; align-items:flex-start; gap:4px;">
                            <span style="color:#38bdf8; font-weight:bold;">${t.proj_prefix} ${item.title}</span>
                            <div style="display:flex; flex-wrap:wrap; gap:8px; margin-left:8px;">
                                ${item.files.map(f => `<a class="file-link" href="/api/download/projects/${f}">📄 ${f.split('/').pop()}</a>`).join('')}
                            </div>
                        </div>
                    `;
                } else {
                    return `
                        <div class="delivery-item">
                            <span>📄 ${item.title}</span>
                            <a class="file-link" href="/api/download/${item.path}">${t.download_btn}</a>
                        </div>
                    `;
                }
            }).join('');
        }

        function prevDelivPage() { if (delivPage > 1) { delivPage--; renderDelivery(); } }
        function nextDelivPage() { const total = Math.ceil(allDeliveryItems.length / delivPageSize); if (delivPage < total) { delivPage++; renderDelivery(); } }

        async function fetchState() {
            try {
                const t = I18N[currentLang];
                const res = await fetch('/api/state');
                const data = await res.json();

                isDaemonRunningCache = data.is_daemon_running;

                const idInput = document.getElementById('t_id');
                const isFocused = (document.activeElement === idInput);
                if (data.next_task_id) {
                    if (!isFocused && (!idInput.value || !userHasEditedId || idInput.value === lastServerTaskId)) {
                        idInput.value = data.next_task_id;
                        lastServerTaskId = data.next_task_id;
                        userHasEditedId = false;
                    }
                }

                document.getElementById('mem_used_text').innerText = data.used_memory_gb + ' GB';
                document.getElementById('mem_total_text').innerText = data.max_memory_gb + ' GB';
                document.getElementById('mem_free_text').innerText = `(${t.free}: ${data.free_memory_gb} GB)`;

                const memInput = document.getElementById('memory_input');
                if (document.activeElement !== memInput && !memInput.value) {
                    memInput.value = data.max_memory_gb;
                }

                const pill = document.getElementById('daemon_status_pill');
                if (data.is_daemon_running) {
                    pill.innerText = t.status_running;
                    pill.style.background = '#065f46';
                    pill.style.color = '#34d399';
                } else {
                    pill.innerText = t.status_stopped;
                    pill.style.background = '#450a0a';
                    pill.style.color = '#f87171';
                }

                allStaff = data.staff || [];
                renderStaff();

                allTasks = data.tasks || [];
                renderTasks();

                allDeliveryItems = data.delivery_items || [];
                renderDelivery();

                document.getElementById('lessons_box').innerHTML = data.lessons.length ? data.lessons.map(l => 
                    `<div style="padding:4px 6px; background:#0b1120; border-radius:4px; margin-bottom:4px;">• [${l.task_id}] ${l.rule}</div>`
                ).join('') : t.no_lessons;

            } catch (err) {
                console.error("狀態同步錯誤:", err);
            }
        }

        async function stopDaemon() {
            const t = I18N[currentLang];
            if (!confirm(t.confirm_stop)) return;
            const res = await fetch('/api/control/stop', { method: 'POST' });
            const data = await res.json();
            alert(data.message);
            fetchState();
        }

        async function resumeDaemon() {
            const res = await fetch('/api/control/resume', { method: 'POST' });
            const data = await res.json();
            alert(data.message);
            fetchState();
        }

        async function retryFailedTasks() {
            const t = I18N[currentLang];
            if (!confirm(t.confirm_retry)) return;
            const res = await fetch('/api/tasks/retry_failed', { method: 'POST' });
            const data = await res.json();
            alert(data.message);
            fetchState();
        }

        async function saveMemory() {
            const t = I18N[currentLang];
            const mem = document.getElementById('memory_input').value;
            const form = new FormData();
            form.append('memory_gb', mem);
            await fetch('/api/config/memory', { method: 'POST', body: form });
            alert(t.alert_mem_saved + mem + ' GB');
            fetchState();
        }

        async function submitTask() {
            const t = I18N[currentLang];
            const title = document.getElementById('t_title').value;
            const desc = document.getElementById('t_desc').value;
            const id = document.getElementById('t_id').value;
            const isProj = document.getElementById('t_proj').checked;
            const fileInput = document.getElementById('t_file');

            if (!title || !desc) {
                alert(t.alert_submit_empty);
                return;
            }

            const form = new FormData();
            form.append('title', title);
            form.append('description', desc);
            form.append('is_project', isProj);
            if (id) form.append('task_id', id);
            if (fileInput.files.length > 0) {
                form.append('file', fileInput.files[0]);
            }

            await fetch('/api/tasks/create', { method: 'POST', body: form });
            alert(t.alert_submit_ok);
            document.getElementById('t_title').value = '';
            document.getElementById('t_desc').value = '';
            document.getElementById('t_file').value = '';
            document.getElementById('t_id').value = '';
            document.getElementById('t_proj').checked = false;
            
            userHasEditedId = false;
            fetchState();
        }

        applyLanguage();
        fetchState();
        setInterval(fetchState, 1500);
    </script>
</body>
</html>
    """

def run():
    uvicorn.run("ui.app:app", host="127.0.0.1", port=8000, reload=False)

if __name__ == "__main__":
    run()