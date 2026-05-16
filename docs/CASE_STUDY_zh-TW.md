# 案例研究：用 AI Agent 取代人類 QA 測試員

> 基於 Amazon Bedrock AgentCore Harness 構建 | 端到端驗證完成

---

## 情境（Situation）

一個開發團隊每天交付前端程式碼。每個 PR 在合併前都需要人工 QA 測試 — 測試員打開瀏覽器、點擊表單、驗證錯誤訊息、檢查排版、撰寫測試報告。這個過程每個 PR 需要 30-60 分鐘，每位 QA 工程師每小時成本 $50-100。

團隊面臨三個問題：
1. **速度** — QA 是瓶頸。PR 等待數小時才有人測試。
2. **成本** — 中型團隊兩位全職 QA 每月成本 $16,000。
3. **一致性** — 人類測試員會遺漏。疲勞、疏忽和標準不一導致 bug 進入生產環境。

核心問題：*AI agent 能否取代人類 QA 測試員 — 不只是檢查元素是否存在，而是真正地點擊按鈕、填寫表單、觀察結果、判斷正確性？*

---

## 任務（Task）

構建一個 AI 驅動的 UI 測試 agent：
- 使用真實瀏覽器導航網頁應用（不只是解析 HTML）
- 像人類一樣與 UI 元素互動（點擊、輸入、滾動、懸停、拖放）
- 通過比較實際行為和預期行為來偵測 bug
- 產生結構化測試報告，附帶證據（截圖、錯誤詳情）
- 自動觸發 Bug-Fix Agent 生成程式碼修補
- 整合到 CI/CD，每個 PR 自動測試

---

## 行動（Action）

### 架構選擇：AgentCore Harness

我們選擇 Amazon Bedrock AgentCore，因為它提供：
- **AgentCore Browser** — agent 控制的遠端雲端 Playwright
- **AgentCore Code Interpreter** — 沙箱 Python 做精確分析
- **AgentCore Memory** — agent 從過去的測試中學習並改進
- **Harness 模式** — 零程式碼宣告式部署（一個 API call）

### 我們構建了什麼

**1. UI Test Agent** — 導航網頁、與元素互動、報告 PASS/FAIL

```python
from strands import Agent
from strands_tools.browser import AgentCoreBrowser

agent = Agent(tools=[AgentCoreBrowser(region="us-east-1").browser])
agent("測試登入頁面。輸入錯誤帳密。驗證錯誤訊息。")
```

**2. Bug-Fix Agent** — 接收失敗報告、分析原始碼、生成修補

```python
client.invoke_harness(
    harnessArn=BUG_FIX_HARNESS_ARN,
    messages=[{"role": "user", "content": [{"text": f"修復這些 bug: {failures}\n原始碼: {code}"}]}]
)
```

**3. CI/CD 整合** — GitHub Actions 在每個 PR 觸發，結果發佈為 PR comment

**4. Demo 前端** — 一個有 5 個故意 bug 的登入頁面用於驗證

### 端到端 Pipeline

```
開發者推送程式碼
    → GitHub Actions 觸發（OIDC → AWS）
    → UI Test Agent 打開瀏覽器，測試頁面
    → Agent 發現 bug：「錯誤訊息是綠色的，應該是紅色」
    → Bug-Fix Agent 生成修補：color:green → color:red
    → 修補準備好提 PR
```

### 測試方法論

Agent 遵循人類 QA 測試員相同的方法論：
1. 導航到頁面
2. 與元素互動（輸入帳密、點擊提交）
3. 觀察結果（出現了什麼？什麼顏色？什麼文字？）
4. 與預期比較
5. 附帶證據報告

我們測試了 **17 種互動類型**：表單提交、下拉選單、動態載入、JavaScript Alert、懸停效果、拖放、無限滾動、鍵盤輸入、iframe 切換、右鍵選單、頁面跳轉、壞圖片偵測、CSS bug 偵測等。

---

## 結果（Result）

### 量化指標

| 指標 | 值 |
|------|-----|
| 總測試數 | 35 |
| 通過率 | 94.3%（33 PASS） |
| 正確偵測的 bug | 3（2 個在我們的 app + 1 個在測試目標） |
| 覆蓋的互動類型 | 17 |
| 每次測試成本 | ~$0.32 |
| 每次測試時間 | ~45 秒 |
| 人類 QA 等效成本 | $50-100/小時 |
| 月省（中型團隊） | ~$15,000 |

### 質化成果

**Agent 像人類 QA 測試員一樣思考：**

測試我們的 demo 登入頁面時，agent 報告：
> 「錯誤訊息文字是**綠色**（rgb(0, 128, 0)），背景是淺紅色。這是一個**雙重 bug**：(1) 錯誤訊息應該用紅色顯示，不是綠色。綠色通常代表成功。(2) 訊息寫『Internal server error』而不是『Invalid username or password』— 這暗示伺服器故障，而不是帳密錯誤。」

這正是一位資深 QA 工程師會寫的報告。

**Bug-Fix Agent 生成正確的修補：**

```diff
- .error-message { color: green; ... }
+ .error-message { color: red; ... }

- errorMsg.textContent = 'Internal server error. Please try again later.';
+ errorMsg.textContent = 'Invalid username or password';
```

兩個修復都是最小化、正確、可直接上線的。

### Pipeline 驗證狀態

| 階段 | 狀態 |
|------|------|
| CI/CD 觸發（GitHub Actions + OIDC） | ✅ 已驗證 |
| UI Test Agent 執行 | ✅ 已驗證 |
| 在自己的應用上偵測 bug | ✅ 已驗證 |
| Bug-Fix Agent 生成修補 | ✅ 已驗證 |
| 測試報告附帶截圖 | ✅ 已驗證 |
| PR comment 發佈 | ✅ 已驗證 |

### Agent 學到了什麼

通過 AgentCore Memory，agent 累積了知識：
- 「SPA 路由切換不會觸發頁面重載 — 等待內容出現，不是等 URL 變化」
- 「有 CSS transition 的下拉選單需要在觸發點擊和選項點擊之間等待」
- 「點擊後找不到元素時，檢查是否有 modal overlay 遮擋」

這些知識跨 session 持久化，改善未來的測試。

---

## 關鍵結論

**AI agent 今天就能取代 80% 的人工 QA 測試** — 不是用脆弱的 Selenium 腳本，而是用對 UI 行為的真正理解。它像人類一樣點擊、像人類一樣判斷、像人類一樣報告 — 每次 $0.32 而不是每小時 $50。

剩餘的 20%（視覺設計審查、主觀 UX 判斷、無障礙審計）仍然需要人類監督，但 agent 處理了那些讓 QA 團隊疲憊的重複性、耗時的驗證工作。

---

*技術棧：Amazon Bedrock AgentCore（Harness + Runtime）、Strands Agents SDK、Claude Sonnet 4.5、AgentCore Browser、AgentCore Code Interpreter、GitHub Actions*

*Repository: https://github.com/timwukp/Harness-agentic-AI-agent-best-practices-and-use-case*
