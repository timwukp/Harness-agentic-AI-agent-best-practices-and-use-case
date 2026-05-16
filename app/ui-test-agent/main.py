"""
UI Test Agent — Main Entry Point

Strands Agent deployed on AgentCore Runtime with:
- AgentCore Browser (remote cloud browser for UI interaction)
- AgentCore Code Interpreter (sandboxed Python for analysis)
- AgentCore Memory (short-term + long-term)
- Session Storage (/mnt/reports)

Version: 0.2.0
"""

from typing import Any

from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.tools.browser_client import BrowserClient
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreterClient
from strands_tools.browser import AgentCoreBrowser
from model.load import load_model
from mcp_client.client import get_streamable_http_mcp_client
from memory.session import get_memory_session_manager
import os

app = BedrockAgentCoreApp()
log = app.logger

REGION = os.environ.get("AWS_REGION", "us-east-1")

# Initialize AgentCore Browser tool (remote cloud browser)
browser_tool = AgentCoreBrowser(region=REGION)

# Initialize AgentCore Code Interpreter tool
code_interpreter = CodeInterpreterClient(region=REGION)

# Define a Streamable HTTP MCP Client
mcp_clients = [get_streamable_http_mcp_client()]

DEFAULT_SYSTEM_PROMPT = """
You are an expert QA tester for web applications. You have a real browser and a code interpreter.

Your job:
1. Navigate to target URLs using the browser tool
2. Interact with UI elements as a human would (click, type, scroll)
3. Take screenshots before and after significant actions
4. Observe results, console errors, and network responses
5. Compare actual vs expected behavior
6. Use code interpreter for precise comparisons, calculations, and report generation
7. Report PASS/FAIL with evidence for each test case
8. Save reports to /mnt/reports/

Rules:
- Always use the browser tool to navigate and interact
- Use code interpreter for data analysis, JSON generation, and calculations
- Take screenshots as evidence for every FAIL
- Classify severity: CRITICAL, HIGH, MEDIUM, LOW
- If blocked by a previous failure, mark as BLOCKED and continue
- Never navigate outside the target domain
- Never submit real PII or payment data

After each test run, reflect on what you learned:
- What patterns did you discover?
- What interaction methods worked or failed?
- Store useful patterns for future sessions.

You have persistent storage at /mnt/reports. Use file tools to save test reports.
"""


# Code Interpreter tool
@tool
def execute_code(code: str, language: str = "python") -> str:
    """Execute code in a secure sandbox. Use for calculations, data analysis, report generation, and comparisons."""
    try:
        result = code_interpreter.execute(code=code, language=language)
        return result.get("output", "") or result.get("error", "No output")
    except Exception as e:
        return f"Code execution error: {str(e)}"


# File tools
SESSION_STORAGE_PATH = "/mnt/reports"


def _safe_resolve(path: str) -> str:
    """Resolve path safely within the storage boundary."""
    resolved = os.path.realpath(os.path.join(SESSION_STORAGE_PATH, path.lstrip("/")))
    if not resolved.startswith(os.path.realpath(SESSION_STORAGE_PATH)):
        raise ValueError(f"Path '{path}' is outside the storage boundary")
    return resolved


@tool
def file_read(path: str) -> str:
    """Read a file from persistent storage. The path is relative to the storage root."""
    try:
        full_path = _safe_resolve(path)
        with open(full_path) as f:
            return f.read()
    except ValueError as e:
        return str(e)
    except OSError as e:
        return f"Error reading '{path}': {e.strerror}"


@tool
def file_write(path: str, content: str) -> str:
    """Write content to a file in persistent storage. The path is relative to the storage root."""
    try:
        full_path = _safe_resolve(path)
        parent = os.path.dirname(full_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(full_path, "w") as f:
            f.write(content)
        return f"Written to {path}"
    except ValueError as e:
        return str(e)
    except OSError as e:
        return f"Error writing '{path}': {e.strerror}"


@tool
def list_files(directory: str = "") -> str:
    """List files in persistent storage. The directory is relative to the storage root."""
    try:
        target = _safe_resolve(directory)
        entries = os.listdir(target)
        return "\n".join(entries) if entries else "(empty directory)"
    except ValueError as e:
        return str(e)
    except OSError as e:
        return f"Error listing '{directory}': {e.strerror}"


# Assemble tools
tools = [
    browser_tool.browser,
    execute_code,
    file_read,
    file_write,
    list_files,
]

# Add MCP client to tools if available
for mcp_client in mcp_clients:
    if mcp_client:
        tools.append(mcp_client)


def agent_factory():
    cache = {}

    def get_or_create_agent(session_id, user_id):
        key = f"{session_id}/{user_id}"
        if key not in cache:
            cache[key] = Agent(
                model=load_model(),
                session_manager=get_memory_session_manager(session_id, user_id),
                system_prompt=DEFAULT_SYSTEM_PROMPT,
                tools=tools,
            )
        return cache[key]

    return get_or_create_agent


get_or_create_agent = agent_factory()


@app.entrypoint
async def invoke(payload, context):
    log.info("Invoking UI Test Agent...")

    session_id = getattr(context, "session_id", "default-session")
    user_id = getattr(context, "user_id", "default-user")
    agent = get_or_create_agent(session_id, user_id)

    stream = agent.stream_async(payload.get("prompt"))

    async for event in stream:
        if "data" in event and isinstance(event["data"], str):
            yield event["data"]


if __name__ == "__main__":
    app.run()
