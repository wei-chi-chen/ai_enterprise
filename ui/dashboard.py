import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import json
import time
from config import EMPLOYEE_ZONE, TASK_ZONE, DELIVERY_ZONE, HISTORY_ZONE
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich import box

console = Console()

def display_kpi_summary():
    kpi_file = HISTORY_ZONE / "performance_kpi.json"
    if not kpi_file.exists():
        return

    try:
        data = json.loads(kpi_file.read_text(encoding="utf-8"))
        total = data.get("total_tasks", 0)
        completed = data.get("completed_tasks", 0)
        failed = data.get("failed_tasks", 0)
        fp_count = data.get("first_pass_count", 0)
        tokens = data.get("total_tokens_generated", 0)
        duration = data.get("total_duration_seconds", 0.0)

        success_rate = (completed / total * 100) if total > 0 else 0.0
        fpy = (fp_count / total * 100) if total > 0 else 0.0
        avg_speed = (tokens / duration) if duration > 0 else 0.0

        p1 = Panel(f"[bold cyan]{total}[/bold cyan] 總任務\n[green]{completed} 成功[/green] / [red]{failed} 失敗[/red]", title="任務交付量", border_style="cyan")
        p2 = Panel(f"[bold green]{success_rate:.1f}%[/bold green] 成功率\n[yellow]一次通過率 (FPY): {fpy:.1f}%[/yellow]", title="品質指標", border_style="green")
        p3 = Panel(f"[bold magenta]{tokens:,}[/bold magenta] Tokens\n[white]推論速度: {avg_speed:.1f} t/s[/white]", title="推論效能", border_style="magenta")
        p4 = Panel(f"[bold blue]{duration/60:.1f}[/bold blue] 分鐘\n[dim]總運行累積時間[/dim]", title="運算耗時", border_style="blue")

        console.print(Columns([p1, p2, p3, p4], expand=True))
    except Exception as e:
        console.print(f"[red]讀取 KPI 失敗: {e}[/red]")

def display_staff_table():
    roster_path = EMPLOYEE_ZONE / "staff_roster.json"
    table = Table(title="🏢 企業虛擬員工編制與硬體配額看板", box=box.ROUNDED, expand=True)
    table.add_column("員工編號", style="cyan", justify="center", width=10)
    table.add_column("職稱", style="bold green", width=22)
    table.add_column("指派模型", style="magenta", width=24)
    table.add_column("核心職責", style="white")

    if roster_path.exists():
        try:
            data = json.loads(roster_path.read_text(encoding="utf-8"))
            for emp in data.get("staff", []):
                table.add_row(emp["id"], emp["title"], emp["model"], emp["role"])
        except Exception as e:
            table.add_row("ERR", "讀取失敗", str(e), "-")
    console.print(table)

def display_task_and_delivery_status():
    backlog_path = TASK_ZONE / "task_backlog.json"
    table_task = Table(title="📋 任務佇列狀態 (task_backlog.json)", box=box.SIMPLE, expand=True)
    table_task.add_column("任務編號", style="cyan", width=12)
    table_task.add_column("任務標題", style="bold", width=30)
    table_task.add_column("狀態", justify="center", width=14)
    table_task.add_column("描述說明", style="dim")

    if backlog_path.exists():
        try:
            tasks = json.loads(backlog_path.read_text(encoding="utf-8"))
            for t in tasks:
                st = t.get("status", "unknown")
                if st == "completed":
                    st_style = "[bold green]completed[/bold green]"
                elif st == "processing":
                    st_style = "[bold yellow]processing[/bold yellow]"
                elif st == "failed":
                    st_style = "[bold red]failed[/bold red]"
                else:
                    st_style = "[white]pending[/white]"
                table_task.add_row(t.get("task_id", "-"), t.get("title", "-"), st_style, t.get("description", "")[:50] + "...")
        except Exception:
            table_task.add_row("-", "無任務或讀取失敗", "-", "-")
    console.print(table_task)

    src_dir = DELIVERY_ZONE / "source_code"
    rep_dir = DELIVERY_ZONE / "reports"
    files = list(src_dir.glob("*.py")) if src_dir.exists() else []
    reports = list(rep_dir.glob("*.md")) if rep_dir.exists() else []

    delivery_info = f"📦 已交付原始碼 ({len(files)} 件):\n" + "\n".join([f"  • {f.name}" for f in files]) if files else "📦 交付區暫無原始碼"
    delivery_info += f"\n\n📄 已交付報告 ({len(reports)} 件):\n" + "\n".join([f"  • {r.name}" for r in reports]) if reports else "\n\n📄 交付區暫無文檔"

    console.print(Panel(delivery_info, title="03_delivery 正式交付成果", border_style="green"))

def display_lessons_learned():
    lessons_path = HISTORY_ZONE / "lessons_learned.json"
    table = Table(title="🧠 組織自我學習與避坑經驗庫 (lessons_learned.json)", box=box.ROUNDED, expand=True)
    table.add_column("任務編號", style="cyan", width=12)
    table.add_column("記錄時間", style="dim", width=20)
    table.add_column("沉澱經驗 / 避坑黃金規則", style="yellow")

    if lessons_path.exists():
        try:
            data = json.loads(lessons_path.read_text(encoding="utf-8"))
            for item in data[-6:]:
                table.add_row(item.get("task_id", "-"), item.get("timestamp", "-"), item.get("rule", "-"))
        except Exception:
            table.add_row("-", "-", "暫無歷史學習記錄")
    console.print(table)

def add_new_task():
    console.rule("[bold cyan]新增研發任務至佇列[/bold cyan]")
    task_id = console.input("[yellow]請輸入任務編號 (例如 TASK-006): [/yellow]").strip()
    if not task_id:
        task_id = f"TASK-{int(time.time())%1000:03d}"
    
    title = console.input("[yellow]請輸入任務標題: [/yellow]").strip()
    desc = console.input("[yellow]請輸入具體需求描述: [/yellow]").strip()
    img = console.input("[yellow]附帶視覺圖片路徑 (選填，無則直接 Enter): [/yellow]").strip()

    backlog_path = TASK_ZONE / "task_backlog.json"
    tasks = []
    if backlog_path.exists():
        try:
            tasks = json.loads(backlog_path.read_text(encoding="utf-8"))
        except Exception:
            tasks = []

    new_task = {
        "task_id": task_id,
        "title": title,
        "description": desc,
        "status": "pending"
    }
    if img:
        new_task["image_path"] = img

    tasks.append(new_task)
    backlog_path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"[bold green]✓ 任務 [{task_id}] 已排入待辦隊列。[/bold green]\n")

def main():
    while True:
        console.clear()
        console.rule("[bold green]Local Autonomous AI Enterprise - 管理控制台[/bold green]")
        display_kpi_summary()
        display_staff_table()
        display_task_and_delivery_status()
        display_lessons_learned()

        console.print("\n[bold]操作選單：[/bold]")
        console.print("1. 重新整理看板狀態")
        console.print("2. 派發新研發任務")
        console.print("3. 清空歷史已完成任務")
        console.print("4. 退出控制台")

        choice = console.input("\n[cyan]請選擇功能 (1-4): [/cyan]").strip()
        if choice == "1":
            continue
        elif choice == "2":
            add_new_task()
            console.input("\n按 Enter 鍵返回主選單...")
        elif choice == "3":
            backlog_path = TASK_ZONE / "task_backlog.json"
            if backlog_path.exists():
                tasks = json.loads(backlog_path.read_text(encoding="utf-8"))
                pending_only = [t for t in tasks if t.get("status") == "pending"]
                backlog_path.write_text(json.dumps(pending_only, ensure_ascii=False, indent=2), encoding="utf-8")
                console.print("[green]已清除非 pending 狀態之歷史任務。[/green]")
                time.sleep(1)
        elif choice == "4":
            console.print("[yellow]已退出控制台。[/yellow]")
            break

if __name__ == "__main__":
    main()