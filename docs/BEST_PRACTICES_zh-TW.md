# AWS Bedrock AgentCore Harness — 最佳實踐指南

> **狀態：** 公開預覽（2026 年 5 月）  
> **CLI 版本：** `@aws/agentcore` v0.14.0  
> **SDK：** `boto3`（`bedrock-agentcore` service client）  
> **可用區域：** us-east-1、us-west-2、eu-central-1、ap-southeast-2

---

## 目錄

1. [什麼時候選擇 AgentCore Harness](#什麼時候選擇-agentcore-harness)
2. [什麼時候不要用 Harness](#什麼時候不要用-harness)
3. [架構決策框架](#架構決策框架)
4. [專案設定最佳實踐](#專案設定最佳實踐)
5. [模型配置](#模型配置)
6. [工具整合](#工具整合)
7. [記憶體策略](#記憶體策略)
8. [環境與 Skills](#環境與-skills)
9. [安全性](#安全性)
10. [成本控制與可觀測性](#成本控制與可觀測性)
11. [開發工作流程](#開發工作流程)
12. [正式環境就緒檢查清單](#正式環境就緒檢查清單)

---

## 什麼時候選擇 AgentCore Harness

### 核心價值主張

AgentCore Harness 取代了建構 agent 運行環境的繁瑣工作。你不需要寫編排程式碼，只需**宣告** agent 要做什麼，AWS 負責處理基礎設施。

### 以下場景選擇 Harness：

| 場景 | 為什麼 Harness 更好 |
|------|---------------------|
| **快速原型開發** | 從想法到運行的 agent 只需幾分鐘，而非幾天 |
| **多模型實驗** | 用設定切換 Bedrock、OpenAI、Gemini — 甚至在對話中途切換 |
| **有狀態的 agent** | 內建記憶體（短期 + 長期）和每個 session 的持久化檔案系統 |
| **人機協作工作流** | Inline function 暫停 agent 並將控制權交回你的程式碼 |
| **需要 shell 的 agent** | 每個 session 有獨立 microVM，含檔案系統 + bash — 可執行腳本、安裝套件、執行程式碼 |
| **沒有基礎設施專業的團隊** | 不需要 Docker、ECS、Lambda 串接 — 只需 `agentcore deploy` |
| **設定驅動的迭代** | 測試 N 種模型/提示詞/工具組合，無需重新部署 |
| **安全的多租戶 agent** | 每個 session 隔離（Firecracker microVM），每個使用者記憶體隔離 |
| **需要瀏覽網頁的 agent** | 內建 Browser 工具，不需要設定 Playwright |
| **需要執行程式碼的 agent** | 內建 Code Interpreter（Python/JS/TS 沙箱） |

### 最適合 Harness 的真實使用案例：

1. **程式碼助手** — agent 需要檔案系統、shell、git、自訂容器
2. **研究 agent** — 瀏覽網頁、綜合發現、跨 session 記憶
3. **資料分析 agent** — 執行 Python、產生圖表、持久化結果
4. **客服 agent** — 多租戶記憶體、透過 inline function 人工升級
5. **DevOps 自動化** — 執行 shell 指令、檢查基礎設施、採取行動
6. **文件處理** — 上傳檔案、用 code interpreter 處理、回傳結果

---

## 什麼時候不要用 Harness

### 以下場景選擇 AgentCore Runtime（自己組裝）：

| 場景 | 為什麼自己組裝更好 |
|------|---------------------|
| **自訂編排邏輯** | 你需要非標準的 agent loop（如多 agent 協調、自訂重試/降級） |
| **嵌入現有應用程式** | 你的 agent 是大型應用程式的一個元件，有自己的 HTTP server |
| **亞秒級延遲需求** | Harness 有 session 啟動開銷（冷啟動約數秒） |
| **自訂串流協議** | 你需要 WebSocket 或 SSE 搭配自訂格式，超出 `InvokeHarness` 提供的範圍 |
| **避免框架鎖定** | 你想完全控制 Strands/LangChain 等的整合方式 |
| **成本敏感的高流量** | 數千個短暫、無狀態的呼叫，microVM 開銷會累積 |

### 以下場景選擇 Bedrock Agents（都不用）：

- 你想要完全無程式碼的解決方案，用主控台設定
- 你的 agent 只需要簡單的工具呼叫，不需要檔案系統/shell
- 你不需要多模型或對話中途切換模型

---

## 架構決策框架

```
┌─────────────────────────────────────────────────────────────┐
│                    你需要...                                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  檔案系統 + Shell 存取？  ──── 是 ──→  HARNESS               │
│         │                                                    │
│         否                                                   │
│         │                                                    │
│  多模型切換？  ──── 是 ──→  HARNESS                           │
│         │                                                    │
│         否                                                   │
│         │                                                    │
│  有狀態 session + 記憶體？  ──── 是 ──→  HARNESS              │
│         │                                                    │
│         否                                                   │
│         │                                                    │
│  自訂編排邏輯？  ──── 是 ──→  AGENTCORE（自己組裝）            │
│         │                                                    │
│         否                                                   │
│         │                                                    │
│  簡單的工具呼叫 agent？  ──── 是 ──→  BEDROCK AGENTS          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 專案設定最佳實踐

### 1. 使用 CLI 建立專案骨架

```bash
# 安裝（穩定版）
npm install -g @aws/agentcore

# 建立專案（第一次建議用互動式精靈）
agentcore create

# 或用非互動式（適合 CI/CD）
agentcore create --name my-agent --model-provider bedrock
```

### 2. 專案結構慣例

```
my-project/
├── agentcore/
│   ├── .env.local              # API 金鑰（已加入 gitignore）
│   ├── agentcore.json          # 資源規格
│   ├── aws-targets.json        # 部署目標（帳號、區域）
│   └── cdk/                    # CDK 基礎設施（自動產生）
├── app/
│   └── <AgentName>/
│       ├── main.py             # Agent 進入點
│       ├── pyproject.toml      # Python 依賴
│       ├── harness.json        # Harness 設定（如果使用 harness）
│       └── model/              # 模型設定
├── .gitignore
└── README.md
```

### 3. Git 衛生

```gitignore
# 永遠加入 gitignore
agentcore/.env.local
agentcore/.cli/
*.pyc
__pycache__/
```

---

## 模型配置

### 最佳實踐：設定合理預設值，呼叫時覆蓋

```bash
# 建立時設定預設模型
agentcore add harness --name my-agent \
  --model-id us.anthropic.claude-sonnet-4-5-20250514-v1:0 \
  --system-prompt "You are a helpful research assistant."

# 特定呼叫時覆蓋（不需重新部署）
agentcore invoke --harness my-agent \
  --model-id us.anthropic.claude-opus-4-5-20251101-v1:0 \
  "需要更強模型的複雜推理任務"
```

### 多模型策略

> **注意：** 如果未指定模型，Harness 預設使用 Claude Sonnet 4.6（`global.anthropic.claude-sonnet-4-6`）。CLI 建立專案時預設使用 Claude Sonnet 4.5（`us.anthropic.claude-sonnet-4-5-20250514-v1:0`）。

| 使用案例 | 建議模型 | 原因 |
|----------|----------|------|
| 一般任務 | Claude Sonnet 4.5/4.6 | 最佳成本/品質平衡 |
| 複雜推理 | Claude Opus 4.5 | 困難問題的更高準確度 |
| 快速查詢 | Claude Haiku | 低延遲、低成本 |
| 程式碼生成 | Claude Sonnet 4.5+ 或 GPT-4.1 | 強大的程式碼能力 |
| 比較測試 | 對話中途切換 | 相同 context，不同模型 |

### 第三方 API 金鑰

```bash
# 存入 Token Vault（永遠不要寫死）
agentcore add credential --type api-key --name my-openai-key --api-key $OPENAI_API_KEY
agentcore deploy

# 呼叫時使用
agentcore invoke --harness my-agent \
  --model-provider open_ai \
  --model-id gpt-4.1 \
  --api-key-arn arn:aws:bedrock-agentcore:us-west-2:123456789012:token-vault/default/apikeycredentialprovider/my-openai-key \
  "你的提示詞"
```

**規則：** 永遠不要把 API 金鑰放在 `harness.json` 或原始碼中。一律使用 AgentCore Identity Token Vault。

---

## 工具整合

### 工具選擇優先順序

1. **先用內建工具** — `shell` 和 `file_operations` 免費且永遠可用
2. **再用 AgentCore 服務** — Browser、Code Interpreter（託管、免設定）
3. **Remote MCP servers** — 用於簡單的外部整合
4. **AgentCore Gateway** — 當你需要認證、策略執行或憑證輪換時
5. **Inline functions** — 用於人機協作或 client-side 邏輯

### 用 `allowedTools` 限制工具

```json
{
  "allowedTools": [
    "@builtin/shell",
    "@builtin/file_operations",
    "@exa/search",
    "@my-gateway/*"
  ]
}
```

**規則：** 正式環境中，永遠明確設定 `allowedTools`。不要留 `*`（允許所有工具）。

### 安全的 MCP Server 連接

```bash
# 不好：寫死 API 金鑰
agentcore add tool --type remote_mcp --name exa \
  --url https://mcp.exa.ai/mcp \
  --header 'x-api-key=sk-live-xxx'

# 好：引用 Token Vault
agentcore add tool --type remote_mcp --name exa \
  --url https://mcp.exa.ai/mcp \
  --header 'x-api-key=${arn:aws:bedrock-agentcore:us-west-2:123456789012:token-vault/default/apikeycredentialprovider/my-exa-key}'
```

### 人機協作的 Inline Functions

```python
# Client-side 處理 inline function 呼叫
response = client.invoke_harness(
    harnessArn=HARNESS_ARN,
    runtimeSessionId=SESSION_ID,
    tools=[{
        "type": "inline_function",
        "name": "approve_action",
        "config": {"inlineFunction": {
            "description": "執行前請求人工核准。",
            "inputSchema": {
                "type": "object",
                "properties": {"action": {"type": "string"}, "risk": {"type": "string"}},
                "required": ["action", "risk"]
            }
        }}
    }],
    messages=[{"role": "user", "content": [{"text": "刪除 staging 資料庫"}]}],
)

# 當 stopReason == "tool_use" 時，在 client-side 處理並回傳結果
```

---

## 記憶體策略

### 預設：讓 CLI 處理

```bash
# 記憶體預設開啟
agentcore create --name my-agent

# 只有明確不需要時才關閉
agentcore create --name stateless-agent --no-harness-memory
```

### 多租戶記憶體搭配 Actor ID

```bash
# 每個使用者有隔離的記憶體
agentcore invoke --harness my-agent --actor-id user-alice --session-id "$(uuidgen)" "你好"
agentcore invoke --harness my-agent --actor-id user-bob --session-id "$(uuidgen)" "你好"
```

**規則：** 多租戶應用中永遠傳入 `actorId`。沒有它，所有使用者會共享同一個記憶體命名空間。

### 長期記憶策略

| 策略 | 使用案例 | 範例 |
|------|----------|------|
| **Semantic（語意）** | 領域事實、知識 | 「客戶偏好 PostgreSQL 而非 MySQL」 |
| **Summarization（摘要）** | Session 摘要 | 「上次 session 我們決定使用 React」 |
| **User Preference（使用者偏好）** | 使用者行為/設定 | 「使用者偏好簡潔的回答」 |
| **Episodic（情節）** | 事件序列 | 「解決部署問題所採取的步驟」 |

### Session 延續模式

```bash
# 模式 1：延續同一對話（重複使用 session ID）
SESSION_ID="$(uuidgen)"
agentcore invoke --harness my-agent --session-id "$SESSION_ID" "開始研究"
agentcore invoke --harness my-agent --session-id "$SESSION_ID" "從上次中斷的地方繼續"

# 模式 2：新 session，同一使用者（長期記憶會延續）
agentcore invoke --harness my-agent --actor-id alice --session-id "$(uuidgen)" "你記得什麼？"
```

### 檔案系統持久化

Harness 支援三種檔案系統類型，讓檔案可以跨 session 保留：

| 類型 | 使用案例 | 需要 VPC |
|------|----------|----------|
| **Session Storage** | 同一 session 內 stop/resume 後仍保留的檔案 | 否 |
| **Amazon EFS** | 跨 session 和 agent 共享的儲存 | 是 |
| **Amazon S3 Files** | 與 S3 bucket 雙向同步 | 是 |

```bash
# Session storage（最簡單 — 不需要 VPC）
agentcore create --name my-agent --session-storage /mnt/data/

# EFS（跨 agent 共享 — 需要 VPC）
# 透過 boto3/AWS CLI 設定 EFS access point ARN
```

**最佳實踐：**
- 用 **Session Storage** 存放 session 內的暫存檔案和中間結果
- 用 **EFS** 當多個 agent 或 harness 需要共享相同檔案時
- 用 **S3 Files** 當你需要在 AgentCore 外部存取檔案時（如下游 pipeline）
- 掛載路徑必須在 `/mnt/` 下

---

## 環境與 Skills

### 用 `InvokeAgentRuntimeCommand` 做確定性工作

```bash
# 不經過模型推理，零 token 成本
agentcore invoke --exec --harness my-agent --session-id "$SID" \
  "pip install pandas && git clone https://github.com/org/repo.git"
```

```python
# boto3 等效寫法
response = client.invoke_agent_runtime_command(
    agentRuntimeArn=HARNESS_ARN,
    runtimeSessionId=SESSION_ID,
    body={"command": "ls -la /workspace"},
)

for event in response["stream"]:
    chunk = event.get("chunk", {})
    if "contentDelta" in chunk:
        delta = chunk["contentDelta"]
        if "stdout" in delta:
            print(delta["stdout"], end="", flush=True)
        if "stderr" in delta:
            print(delta["stderr"], end="", flush=True)
    elif "contentStop" in chunk:
        print(f"\n[exit code: {chunk['contentStop']['exitCode']}]")
```

**規則：** 用 `--exec` 做設定、清理和確定性腳本。把模型呼叫留給推理任務。

### 環境變數

在 `harness.json` 中設定環境變數：

```json
{
  "environmentVariables": {
    "MY_API_URL": "https://api.example.com",
    "LOG_LEVEL": "debug"
  }
}
```

```bash
agentcore deploy  # 套用變更
```

**規則：** 用環境變數存放非機密設定。用 Token Vault 存放機密資訊。

### 自訂容器最佳實踐

```dockerfile
# 必須是 linux/arm64
FROM --platform=linux/arm64 python:3.12-slim

# 安裝你的依賴
RUN pip install pandas numpy scikit-learn
RUN apt-get update && apt-get install -y git curl

# 加入你的原始碼
COPY ./src /workspace/src

# 不要設定 ENTRYPOINT/CMD — harness 會覆蓋它們
```

```bash
agentcore create --name ml-agent --container ./Dockerfile
agentcore deploy
```

### Skills 用於領域知識

```bash
# 烘焙進容器（正式環境建議）
# 或在 session 開始時安裝：
agentcore invoke --exec --harness my-agent --session-id "$SID" \
  "npx @anthropic-ai/agent-skills add xlsx github"

# 將 harness 指向 skills
agentcore add harness --name my-agent --skill-path .agents/skills/xlsx
```

---

## 安全性

### 執行角色 — 最小權限原則

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
```

**規則：** 只授予 agent 實際需要的權限。從最小開始，按需增加。

### IAM 雙重權限模型

每個 Harness API 都需要**同時**具備 harness 資源和底層 Runtime 資源的權限：

| API | 需要的 IAM Actions |
|-----|-------------------|
| `InvokeHarness` | `bedrock-agentcore:InvokeHarness` + `bedrock-agentcore:InvokeAgentRuntime` |
| `InvokeAgentRuntimeCommand` | `bedrock-agentcore:InvokeAgentRuntimeCommand` + `bedrock-agentcore:InvokeAgentRuntime` |
| `CreateHarness` | `bedrock-agentcore:CreateHarness` + `bedrock-agentcore:CreateAgentRuntime` |
| `UpdateHarness` | `bedrock-agentcore:UpdateHarness` + `bedrock-agentcore:UpdateAgentRuntime` |
| `DeleteHarness` | `bedrock-agentcore:DeleteHarness` + `bedrock-agentcore:DeleteAgentRuntime` |

**規則：** 為 harness 呼叫者撰寫 IAM policy 時，永遠要包含兩個 action。缺少 Runtime action 會導致 AccessDenied。

### 多租戶的 Inbound OAuth

```bash
agentcore add harness --name my-agent \
  --authorizer-type CUSTOM_JWT \
  --discovery-url https://cognito-idp.us-west-2.amazonaws.com/<POOL_ID>/.well-known/openid-configuration \
  --allowed-clients <CLIENT_ID>
```

**規則：** 當你需要 per-user credential scoping 給下游工具時，使用 OAuth（不只是 SigV4）。

### 存取私有資源的 VPC

```bash
agentcore add harness --name internal-agent \
  --network-mode VPC \
  --subnets subnet-0abc1234 \
  --security-groups sg-0abc1234
```

**重要：** VPC 模式需要 NAT gateway 來存取 ECR Public（`public.ecr.aws`）。

### Gateway 策略（Cedar）

使用 AgentCore Gateway + Cedar 策略來控制：
- 誰可以呼叫哪個工具
- 在什麼條件下
- 用什麼參數

---

## 成本控制與可觀測性

### 設定硬性限制

```bash
# maxIterations：預設 75 — 每次 invoke 的推理/行動循環上限
# timeout：預設 3600（1 小時）— 單次 invoke 超時
# max-tokens：預設無 — 每次 invoke 的 token 預算
# idle-timeout：預設 900（15 分鐘）— 閒置 microVM 保活時間
# max-lifetime：預設 28800（8 小時）— microVM 最大存活時間

agentcore add harness --name my-agent \
  --max-iterations 50 \
  --timeout 1800 \
  --max-tokens 8192 \
  --idle-timeout 600 \
  --max-lifetime 14400 \
  --truncation-strategy sliding_window
```

**規則：** 正式環境中永遠設定 `maxIterations` 和 `timeoutSeconds`。失控的 agent 迴圈可能很昂貴。

### 成本優化技巧

| 技巧 | 影響 |
|------|------|
| 用 `--exec` 做確定性工作 | Shell 指令零 token 成本 |
| 保守設定 `maxIterations` | 防止無限迴圈 |
| 簡單任務用 Haiku | 比 Opus 便宜 10 倍 |
| 設低 `idleRuntimeSessionTimeout` | 減少閒置 microVM 成本 |
| 用 `truncation-strategy: summarization` | 長 session 中減少 context window 大小 |

### 可觀測性（零設定）

```bash
# 串流日誌
agentcore logs --harness my-agent

# 過濾錯誤
agentcore logs --harness my-agent --since 1h --level error

# 列出追蹤
agentcore traces list --harness my-agent

# 取得特定追蹤
agentcore traces get <trace-id> --harness my-agent
```

所有追蹤自動流向 CloudWatch。啟用 Transaction Search（每個帳號一次性設定）即可查詢。

### 成本分配標籤

```json
{
  "tags": {
    "team": "platform",
    "environment": "production",
    "cost-center": "engineering"
  }
}
```

---

## 開發工作流程

### 建議流程

```
1. agentcore create          → 建立專案骨架
2. 編輯 harness.json         → 設定模型、工具、記憶體
3. agentcore dev             → 本地開發伺服器 + inspector UI
4. 迭代設定                   → 覆蓋不需要重新部署
5. agentcore deploy          → 推送到 AWS
6. agentcore invoke          → 測試已部署的 agent
7. agentcore logs            → 監控
8. agentcore run eval        → 評估品質
```

### 本地開發

```bash
agentcore dev
# 在 localhost:8080 開啟瀏覽器 inspector
# 與 agent 對話、檢查追蹤、即時覆蓋設定
```

### 測試多種設定

```bash
# 測試不同模型，無需重新部署
agentcore invoke --harness my-agent --model-id us.anthropic.claude-sonnet-4-5-20250514-v1:0 "測試提示詞"
agentcore invoke --harness my-agent --model-id gpt-4.1 --model-provider open_ai "相同測試提示詞"

# 測試不同系統提示詞
agentcore invoke --harness my-agent --system-prompt "簡潔回答。" "解釋量子計算"
agentcore invoke --harness my-agent --system-prompt "詳細回答。" "解釋量子計算"
```

---

## 正式環境就緒檢查清單

- [ ] **限制已設定：** `maxIterations`、`timeoutSeconds`、`maxTokens` 已配置
- [ ] **工具已限制：** `allowedTools` 明確定義（不是 `*`）
- [ ] **密鑰在 Token Vault：** 任何地方都沒有寫死的 API 金鑰
- [ ] **OAuth 已設定：** 如果是多租戶，已啟用 inbound JWT authorizer
- [ ] **VPC 已設定：** 如果存取私有資源
- [ ] **記憶體已隔離：** 多租戶隔離有傳入 `actorId`
- [ ] **標籤已套用：** 用於成本分配和存取控制
- [ ] **截斷策略已設定：** `sliding_window` 或 `summarization`
- [ ] **可觀測性已驗證：** CloudWatch Transaction Search 已啟用
- [ ] **評估器已設定：** Online eval 用於持續品質監控
- [ ] **自訂容器已測試：** 如果使用自訂環境，已在 `linux/arm64` 上驗證
- [ ] **錯誤處理：** Client 處理串流中的 `runtimeClientError` 事件
- [ ] **Session ID 策略：** 已記錄 session ID 如何產生和重複使用

---

## SDK 參考

### Harness API（boto3）

```python
import boto3

# 控制平面
control = boto3.client("bedrock-agentcore-control", region_name="us-west-2")
control.create_harness(harnessName="...", executionRoleArn="...")
control.get_harness(harnessId="...")
control.update_harness(harnessId="...", maxIterations=50)
control.delete_harness(harnessId="...")
control.list_harnesses()

# 資料平面
data = boto3.client("bedrock-agentcore", region_name="us-west-2")
data.invoke_harness(harnessArn="...", runtimeSessionId="...", messages=[...])
data.invoke_agent_runtime_command(agentRuntimeArn="...", runtimeSessionId="...", body={"command": "..."})
```

### 支援的 SDK

| SDK | Service Client | 狀態 |
|-----|---------------|------|
| **Python（boto3）** | `bedrock-agentcore` / `bedrock-agentcore-control` | GA |
| **Kotlin** | `BedrockAgentCoreClient` | GA |
| **JavaScript** | `@aws-sdk/client-bedrock-agentcore` | GA |
| **CLI** | `aws bedrock-agentcore-control` / `aws bedrock-agentcore` | GA |
| **AgentCore CLI** | `@aws/agentcore`（npm） | v0.14.0 |

---

## 定價

- **無額外 Harness 費用** — 你只為使用的底層 AgentCore 功能付費
- 模型呼叫按 token 計費（Bedrock 定價）
- Code Interpreter、Browser、Memory 按使用量計費
- MicroVM 運算包含在 AgentCore Runtime 定價中

---

*最後更新：2026-05-16*
