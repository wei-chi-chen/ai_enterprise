import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import json
import shutil
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from config import TASK_ZONE, DELIVERY_ZONE, HISTORY_ZONE, WORKSPACE_DIR
from agents.employee import EnterpriseStaffManager

console = Console()

def run_web_dashboard():
    """Launch the Web Dashboard & API Server (啟動 Web 控制台與 API 服務)"""
    console.print("[bold green]Starting Web Dashboard (正在啟動 Web 控制台)...[/bold green]")
    console.print("[cyan]Access Dashboard at (訪問地址): http://127.0.0.1:8000[/cyan]\n")
    uvicorn.run("ui.app:app", host="127.0.0.1", port=8000, reload=False)

def initialize_system():
    """Reset & Initialize Virtual Staff Roster (初始化 / 重置虛擬員工名冊)"""
    console.print("[bold yellow]Initializing System & Staff Roster (正在重置並初始化系統與員工名冊)...[/bold yellow]")
    staff_mgr = EnterpriseStaffManager()
    staff_mgr._init_default_roster()
    console.print("[bold green]✔ Successfully initialized 12 virtual agent profiles (已成功重置 12 位虛擬專員預設配置)！[/bold green]\n")

def reset_tasks_and_delivery():
    """Reset Task Backlog and Clear All Deliveries (清空任務隊列與交付成果，序號回歸 TASK-001)"""
    confirm = Prompt.ask(
        "[bold red]Are you sure you want to PURGE all tasks and deliverables? (確定要清空所有任務與交付成果嗎？)[/bold red]",
        choices=["y", "n"],
        default="n"
    )
    if confirm.lower() != "y":
        console.print("[dim]Operation cancelled (操作已取消)。[/dim]\n")
        return

    backlog_file = TASK_ZONE / "task_backlog.json"
    backlog_file.write_text("[]", encoding="utf-8")

    (TASK_ZONE / "daemon_control.json").write_text(
        json.dumps({"stop_requested": False, "is_running": False}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    (TASK_ZONE / "memory_usage.json").write_text(json.dumps({"used_memory_gb": 0.0}), encoding="utf-8")
    (TASK_ZONE / "daemon.pid").unlink(missing_ok=True)

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

    delivery_subdirs = ["source_code", "reports", "spreadsheets", "projects"]
    for sub in delivery_subdirs:
        sub_path = DELIVERY_ZONE / sub
        if sub_path.exists():
            for item in sub_path.iterdir():
                if item.name != ".gitkeep":
                    try:
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
                    except Exception:
                        pass

    upload_dir = WORKSPACE_DIR / "uploads"
    if upload_dir.exists():
        for item in upload_dir.iterdir():
            if item.name != ".gitkeep":
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                except Exception:
                    pass

    console.print("\n[bold green]✔ Successfully purged all tasks and delivery items (已成功清空所有任務與交付成果)！[/bold green]")
    console.print("[bold cyan]✔ Task sequence reset to TASK-001 (任務編號已重置為 TASK-001 起始)。[/bold cyan]\n")

def retry_failed_tasks():
    """Purge completed tasks, reset failed tasks to pending, and reindex sequentially (清除已完成任務，重整失敗任務序號並重試)"""
    backlog_file = TASK_ZONE / "task_backlog.json"
    if not backlog_file.exists():
        console.print("[yellow]No tasks found (找不到任務檔案)。[/yellow]\n")
        return

    try:
        tasks = json.loads(backlog_file.read_text(encoding="utf-8"))
    except Exception:
        tasks = []

    # 篩選出未完成或失敗的任務
    retry_list = [t for t in tasks if t.get("status") in ["failed", "pending", "processing"]]
    if not retry_list:
        console.print("[yellow]No failed or pending tasks to retry (目前沒有失敗或待處理的任務)。[/yellow]\n")
        return

    # 重新連續編號：TASK-001, TASK-002 ...
    for idx, t in enumerate(retry_list, start=1):
        old_id = t.get("task_id")
        new_id = f"TASK-{idx:03d}"
        t["task_id"] = new_id
        t["status"] = "pending"
        # 若有圖片路徑包含舊 ID，同步更名
        if t.get("image_path") and old_id:
            old_img = Path(t["image_path"])
            if old_img.exists() and old_id in old_img.name:
                new_img_name = old_img.name.replace(old_id, new_id)
                new_img_path = old_img.parent / new_img_name
                old_img.rename(new_img_path)
                t["image_path"] = str(new_img_path)

    # 寫回 backlog
    backlog_file.write_text(json.dumps(retry_list, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # 清理 02_tasks 中的半成品資料夾
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

    console.print(f"\n[bold green]✔ Successfully pruned completed tasks. {len(retry_list)} failed task(s) reset to pending starting from TASK-001![/bold green]")
    console.print("[bold cyan](已移除已完成任務，並將失敗任務從 TASK-001 開始重新排列就緒！)[/bold cyan]\n")

def main():
    while True:
        console.clear()
        welcome_text = """[bold cyan]Local Autonomous AI Enterprise (本地自主 AI 企業平台)[/bold cyan]
[dim]Fully Local Multi-Agent Autonomous Development Framework (純本地多 Agent 自主研發框架)[/dim]

[1] Launch Web Dashboard (啟動 Web 控制台) [Default: 127.0.0.1:8000]
[2] Initialize / Reset Staff Roster (初始化 / 一鍵重置 12 位虛擬員工配置)
[3] Reset & Clear Tasks / Delivery (清空任務隊列與交付成果，重置為 TASK-001)
[4] Retry Failed Tasks (清理已完成任務，失敗任務重置序號為 TASK-001 並重試)
[5] Exit System (退出系統)"""

        console.print(Panel(welcome_text, title="Main Control Console (主控制台)", border_style="cyan"))
        choice = Prompt.ask("Please enter your choice (請輸入選項)", choices=["1", "2", "3", "4", "5"], default="1")

        if choice == "1":
            run_web_dashboard()
            break
        elif choice == "2":
            initialize_system()
            Prompt.ask("\nPress Enter to return to menu (按 Enter 鍵返回主選單)...")
        elif choice == "3":
            reset_tasks_and_delivery()
            Prompt.ask("\nPress Enter to return to menu (按 Enter 鍵返回主選單)...")
        elif choice == "4":
            retry_failed_tasks()
            Prompt.ask("\nPress Enter to return to menu (按 Enter 鍵返回主選單)...")
        elif choice == "5":
            console.print("[bold red]System shutting down. Goodbye (系統已安全關閉，再見)！[/bold red]")
            break

if __name__ == "__main__":
    main()