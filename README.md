> [!NOTE]
> **繁體中文**：全新進階版本 **[ai_enterprise2](https://github.com/wei-chi-chen/ai_enterprise2)** 現已推出！包含全新架構規劃、多模型並行排程優化與更強的容錯機制，歡迎前往新專案體驗。
> 
> **English**: The next-generation version, **[ai_enterprise2](https://github.com/wei-chi-chen/ai_enterprise2)**, is now live! Featuring advanced memory scheduling, autonomous role-based model escalation, and an updated enterprise console. Explore the new repository at [ai_enterprise2](https://github.com/wei-chi-chen/ai_enterprise2).
<img width="1917" height="867" alt="螢幕擷取畫面 2026-10-31 120256" src="https://github.com/user-attachments/assets/362cde45-c661-4e68-9d78-683638120d23" />

---

# Local Autonomous AI Enterprise (本地自主 AI 企業平台)
<img width="1917" height="857" alt="螢幕擷取畫面 2026-10-29 193240" src="https://github.com/user-attachments/assets/fd3de236-0cf2-4f94-be23-5f292510f7c1" />
<img width="1851" height="867" alt="螢幕擷取畫面 2026-10-29 064533" src="https://github.com/user-attachments/assets/104d0d4c-ab8e-405b-9aa8-69a2de397c3b" />
> **Language / 語言說明**  
> This documentation provides both **Traditional Chinese (繁體中文)** and **English (英文)** guides below.  
> 本專案說明文件於開頭與各章節均提供繁體中文與英文雙語對照解說，方便全球開源社群共同審閱與協作。

---

## 繁體中文說明 (Traditional Chinese)

### 一、 專案定位與核心理念

**Local Autonomous AI Enterprise** 是一個 100% 離線運行的多代理人（Multi-Agent）自主研發與軟體生產框架。

> ⚠️ **重要架構聲明：本專案本質上是提供一套「高度彈性、自動防禦與自適應調度的 Multi-Agent 架構」**。  
> 預設的 12 位員工與推薦模型僅是官方提供的一套開箱即用範例。**本專案中所有維度皆能完全自訂**：
> 1. **員工數量與職能編制**：想縮減至 3 位精簡團隊，或擴展至 20 位專門領域專員皆可自由增刪。
> 2. **模型自由選擇**：每個員工要掛載 Qwen、DeepSeek、Llama、LLaVA 或是你自行訓練的微調模型，完全由設定檔決定。
> 3. **硬體記憶體預算**：自適應配額，8GB、16GB、32GB、48GB 到 128GB+ 皆可在控制台隨調即用。
> 4. **並行任務槽位**：系統會根據當前機器配置自動換算槽位，亦可手動強制指定同時並行處理的任務上限。

我們深信未來的硬體記憶體（RAM/VRAM）技術將會爆發式普及並大幅降價。本專案堅定押注於**「完全離線、純開源且永久免費」**的本機自主智慧體架構。在不久的將來，個人電腦即可從容運行 70B 甚至更大參數量的多代理人體系，本專案即是通往該未來的實踐基石。

---

### 二、 作業系統支援性說明

* **目前主要支援環境**：**Windows 10 / 11 (x64)**
* **說明**：本框架深度整合了 Windows 系統的原生行程管理（包含 `taskkill`、Windows API `OpenProcess` PID 狀態追蹤、以及獨立 Console 控制台視窗調度）。Linux 與 macOS 底層已保留基本相容程式碼，但尚未經完整實機驗收，歡迎開源社群提交跨平台相容 PR！

---

### 三、 預設推薦安裝之 Ollama 模型（範例配置）

若想直接體驗官方預設的 12 人虛擬研發團隊，請於本地 Ollama 預先拉取以下開源模型：

```bash
# 核心大腦（總架構師 EMP-01、研發主管 EMP-02、仲裁長 EMP-03）
ollama pull qwen2.5:32b
ollama pull qwen2.5-coder:32b

# 核心骨幹（全端開發 EMP-04、測試工程師 EMP-05、代碼審查員 EMP-06）
ollama pull qwen2.5-coder:14b

# 多模態視覺感知（視覺專員 EMP-08）
ollama pull llava:latest

# 文檔編寫與行政秘書（文案專家 EMP-09、行政秘書 EMP-10）
ollama pull llama3.1:8b

# 輕量稽核、資料處理與分流（資安稽核員 EMP-07、資料分析員 EMP-11、任務分流員 EMP-12）
ollama pull qwen2.5:7b
```

#### 端看個人硬體配備，一切皆可自訂：
* **頂規配備（64GB+ RAM / 24GB+ VRAM）**：可全面將員工替換為 32B 甚至 70B 模型。
* **標準配備（32GB ~ 48GB RAM）**：使用預設之 32B + 14B + 8B + 7B 階梯式混合集群。
* **輕量入門（16GB ~ 24GB RAM）**：修改 `staff_roster.json`，將架構師改為 14B，開發人員改為 7B 或 `deepseek-coder:6.7b`，控制台記憶體配額設定為 16GB，依然能順暢運行。

---

### 四、 專案優缺點客觀分析

#### 🌟 核心優勢 (Strengths)
1. **沙盒 TDD 自動檢查閉環**：代碼並非「生成即交付」，每項任務必須在 `ExecutionSandbox` 沙盒環境中通過獨立執行的單元測試（`test_suite.py`），語法錯誤或斷言失敗絕不放行。
2. **三級主管階梯重構機制 (Tier 1~3 Escalation)**：初次測試未過時，依序由 EMP-06 審查員（14B）自修 $\to$ EMP-02 研發主管（32B）重構 $\to$ EMP-03 仲裁長（32B）終裁重寫。
3. **長效無人值守運作 (Long-Running Autonomy)**：內建自動清理暫存、進程鎖防護（PID）、斷點重啟續跑、即時連線 Ollama `/api/ps` 顯存動態平衡，可長時間不間斷自動消化任務隊列。
4. **絕對隱私與零 Token 成本**：完全基於本地推理，企業內部代碼、業務資料與試算表永不出網，無任何雲端 API 呼叫費用。

#### ⚠️ 現存劣勢 (Weaknesses & Limitations)
1. **本機推理速度較慢**：受限於本機硬體算力，混合推論（特別是 32B 模型冷啟動或多次階梯重構時），單項任務可能需耗時 10 至 30 分鐘，遠慢於商業雲端叢集。
2. **硬體記憶體敏感度高**：當並行槽位過多或模型切換頻繁時，容易引發作業系統虛擬記憶體換頁（Swap），造成暫時性延遲。
3. **小模型代碼能力浮動**：中小型模型（7B/14B）在初次規劃邊界時偶有瑕疵，需依賴沙盒升級機制由主管介入糾偏。

---

### 五、 當前已知問題 (Known Issues)

1. **嚴苛數值/統計斷言邊界爭議**：
   在純數值計算或統計演算法（如 IQR 離群值過濾 `remove_outliers`）中，若架構師模型在 `test_suite.py` 內寫死了精準數值，下游模型產出的演算法可能因四分位插值定義微異（線性內插 vs 盒鬚切分）導致 `AssertionError`。目前已開放 Tier 3 仲裁長修正測試用例之權限。
2. **跨模組建構子參數同步**：
   多檔案專案生成時，雖然已將前置檔案上下文擴大至 4000 字元，但若模組數量過多，仍有偶發性類別參數微小脫節的可能。

---

### 六、 詳細安裝與使用教學

#### 1. 前置準備
* **作業系統**：Windows 10 / 11 64-bit
* **環境依賴**：Python 3.10 或 3.11、Git、最新版 Ollama ([ollama.com](https://ollama.com))

#### 2. 安裝步驟
```powershell
# 1. 複製儲存庫
git clone https://github.com/wei-chi-chen/ai_enterprise.git
cd ai_enterprise

# 2. 建立並啟用虛擬環境
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. 安裝必要套件
pip install fastapi uvicorn httpx rich gitpython matplotlib pandas openpyxl python-multipart
```

#### 3. 啟動主控制台
```powershell
python main.py
```
* 輸入 **`1`**：啟動 Web 控制台（預設位址：`http://127.0.0.1:8000`）。
* 輸入 **`2`**：初始化 / 重置 12 位虛擬員工名冊與狀態。
* 輸入 **`3`**：清空所有任務與交付成果，任務序號重置為 `TASK-001`。
* 輸入 **`4`**：清理已完成任務，將失敗/待處理任務重新自 `TASK-001` 編號並重試。
* 輸入 **`5`**：安全退出系統。

#### 4. 派發任務與成果交付
1. 進入 Web 介面（`http://127.0.0.1:8000`），填寫標題與需求描述（可勾選「多檔案專案」或上傳圖片/Excel）。
2. 點擊右上角 **「▶ 繼續 / 啟動執行」**，背景排程器（`daemon.py`）即刻自適應啟動。
3. 任務通過驗證後，正式檔案自動交付至 `enterprise_workspace/03_delivery/`，可直接於網頁點擊下載。

---

## English Documentation

### I. Architecture Overview & Philosophy

**Local Autonomous AI Enterprise** is a 100% offline, multi-agent autonomous software engineering platform.

> ⚠️ **Core Concept: This project provides a flexible, self-healing, multi-agent architectural framework.**  
> The default 12 agents and recommended models are purely an out-of-the-box demonstration. **Everything in this framework is completely customizable**:
> 1. **Agent Count & Roles**: Scale up to 20 agents or down to 3 agents as needed.
> 2. **Model Selection**: Assign any local model (Qwen, DeepSeek, LLaVA, Llama, or fine-tuned weights) per agent.
> 3. **Hardware Quota**: Fully adaptive RAM/VRAM limits (8GB, 16GB, 32GB, 48GB, 128GB+).
> 4. **Concurrency**: Dynamic admission control automatically determines parallel task slots.

We firmly believe in the imminent proliferation and affordability of high-capacity memory hardware. This project is committed to a **100% offline, free, and open-source** local multi-agent future.

---

### II. Platform Support

* **Primary Supported OS**: **Windows 10 / 11 (x64)**  
* *Note*: The engine is optimized for Windows process management (`taskkill`, win32 API PID checks, console allocation). POSIX fallback code is present, but complete cross-platform PRs are warmly welcomed.

---

### III. Advantages & Trade-Offs

#### 🌟 Key Advantages
* **Strict TDD Sandbox Verification**: Code is executed inside `ExecutionSandbox` before delivery.
* **Tier 1 to Tier 3 Escalation**: Automated progressive bug fixing (Reviewer 14B $\to$ Tech Lead 32B $\to$ Chief Arbiter 32B).
* **Zero Cloud Costs & 100% Privacy**: Completely local execution; zero commercial API dependency.
* **Long-Running Reliability**: Real-time Ollama VRAM synchronization, PID tracking, and graceful restart recovery.

#### ⚠️ Trade-Offs
* **Inference Latency**: Significantly slower than commercial cloud APIs on consumer hardware.
* **Memory Sensitivity**: Frequent model swapping under heavy load can lead to OS memory paging (swap).

---

### IV. Quick Start Guide

```powershell
# 1. Clone & Setup
git clone https://github.com/wei-chi-chen/ai_enterprise.git
cd ai_enterprise
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Install Dependencies
pip install fastapi uvicorn httpx rich gitpython matplotlib pandas openpyxl python-multipart

# 3. Launch Console
python main.py
```

---

---

## 🗺️ Roadmap & Future Capabilities

We are actively exploring and planning the following capabilities:

- [ ] **Cross-Platform Containerization**: Encapsulate sandboxes within Docker containers to enable universal POSIX/Linux/macOS support.
- [ ] **Autonomous Web/API Fallback Assistance (Self-Evolution)**:
  - When Tier 3 escalation fails to resolve complex architectural bugs or strict mathematical assertions locally, the system will autonomously spawn a headless browser / external sandbox session to query external intelligence sources (e.g., Gemini, ChatGPT).
  - The external reasoning process and debugging steps will be logged into a persistent local knowledge base (RAG/Vector DB) to improve future offline self-healing runs without repeated external queries.
- [ ] **Dynamic Assertion Relaxer**: Introduce an automated heuristic layer to prevent the Architect agent from setting overly brittle floating-point unit tests.
- [ ] **Diff-Based Patching**: Move from full-file rewrites to unified diff/patch applications to lower generation latency and memory pressure.

> Have thoughts on the architecture or want to help implement these? Feel free to open an **RFC Issue** or start a discussion!

### 作者與聯絡方式 (Author & Contact)

* **Maintainer / 作者**：陳威齊
* **Email**：[03260326max@gmail.com](mailto:03260326max@gmail.com)
* **Contributions**：歡迎提交 Issue 與 Pull Request 共同改進模型斷言容錯與跨平台調度機制！

### 授權協議 (License)
This project is licensed under the **MIT License**.
