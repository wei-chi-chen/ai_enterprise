import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import json
import time
from config import TASK_ZONE, HISTORY_ZONE
from daemon import EnterpriseDaemon
from rich.console import Console
from rich.table import Table

console = Console()

BENCHMARK_TASKS = [
    {
        "task_id": "BENCH-001",
        "title": "LRU Cache Implementation",
        "description": "實作一個具備 get(key) 與 put(key, value) 的 LRUCache 類別，當快取容量超過 capacity 時，必須逐出最久未使用的項目。時間複雜度需為 O(1)。",
        "status": "pending"
    },
    {
        "task_id": "BENCH-002",
        "title": "Markdown Table to JSON Converter",
        "description": "撰寫函式 md_table_to_json(md_text: str) -> list[dict]，將 Markdown 表格字串精確解析為 Python 字典串列，自動處理欄位去除首尾空白與型別推論。",
        "status": "pending"
    },
    {
        "task_id": "BENCH-003",
        "title": "Rate Limiter Token Bucket",
        "description": "實作 TokenBucketRateLimiter 類別，支援 acquire(tokens=1) -> bool 方法，依據設定的 refill_rate 每秒自動補充權杖，達上限時不溢出。",
        "status": "pending"
    }
]

def run_benchmark():
    console.rule("[bold cyan]啟動 AI Enterprise 標準能力基準評測 (Benchmark)[/bold cyan]")
    
    # 寫入基準任務
    backlog_path = TASK_ZONE / "task_backlog.json"
    backlog_path.write_text(json.dumps(BENCHMARK_TASKS, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"[green]已注入 {len(BENCHMARK_TASKS)} 個標準評測題目至待辦隊列。[/green]\n")

    # 執行 Daemon 排程
    start_time = time.time()
    daemon = EnterpriseDaemon()
    daemon.run_queue_until_empty()
    total_time = time.time() - start_time

    # 讀取並彙整結果
    kpi_file = HISTORY_ZONE / "performance_kpi.json"
    tasks_res = []
    if kpi_file.exists():
        try:
            data = json.loads(kpi_file.read_text(encoding="utf-8"))
            tasks_res = [t for t in data.get("tasks_history", []) if t["task_id"].startswith("BENCH-")]
        except Exception:
            pass

    # 繪製評測成績單
    table = Table(title="🏆 企業基準評測成績單 (Benchmark Scorecard)")
    table.add_column("題目編號", style="cyan")
    table.add_column("任務標題", style="white")
    table.add_column("執行結果", justify="center")
    table.add_column("一次通過率 (FPY)", justify="center")
    table.add_column("升級層級", justify="center")
    table.add_column("耗時 (秒)", justify="right")

    success_cnt = 0
    fpy_cnt = 0

    for r in tasks_res:
        succ = r.get("success", False)
        fp = r.get("first_pass", False)
        if succ:
            success_cnt += 1
        if fp:
            fpy_cnt += 1

        succ_text = "[bold green]PASS[/bold green]" if succ else "[bold red]FAIL[/bold red]"
        fpy_text = "[green]YES[/green]" if fp else "[yellow]NO (Escalated)[/yellow]"
        table.add_row(
            r.get("task_id", "-"),
            r.get("title", "-"),
            succ_text,
            fpy_text,
            str(r.get("escalation_tier", 0)),
            f"{r.get('duration', 0.0):.1f}s"
        )

    console.print("\n")
    console.print(table)
    
    total_bench = len(BENCHMARK_TASKS)
    pass_rate = (success_cnt / total_bench) * 100 if total_bench > 0 else 0
    fpy_rate = (fpy_cnt / total_bench) * 100 if total_bench > 0 else 0

    console.print(f"\n[bold]總結指標：[/bold]")
    console.print(f"• 解決率 (Pass@1): [bold green]{pass_rate:.1f}%[/bold green]")
    console.print(f"• 初次驗收通過率 (FPY): [bold yellow]{fpy_rate:.1f}%[/bold yellow]")
    console.print(f"• 總評測耗時: [cyan]{total_time/60:.2f} 分鐘[/cyan]\n")

if __name__ == "__main__":
    run_benchmark()