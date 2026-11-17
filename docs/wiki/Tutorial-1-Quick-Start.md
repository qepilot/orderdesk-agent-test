# Tutorial 1: Quick start

**Goal:** run the course agent on your machine in about ten minutes, first with no model at all, then with Claude.
**You need:** Python 3.12 or newer and git. Nothing else for the first two steps.

## 1. Get the code and install

```bash
git clone https://github.com/qepilot/orderdesk-agent-test.git
```

```bash
cd orderdesk-agent-test
```

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-agent.txt
```

`requirements-agent.txt` is the small set (`httpx`, `pydantic`, `python-dotenv`) that the agent needs. The full `requirements.txt` adds Jupyter, LangGraph and the MCP SDK for the course notebooks.

## 2. Run it with no model

The labs ship with a scripted stand-in that plays the model. Everything around it is real: the tools, the harness, the guards, the evidence check.

```bash
python -m assistant investigate 101
```

You see each step the agent takes (`MODEL ... -> run_sql`, `TOOL ok run_sql(...)`), then findings with evidence quoted from tool results. The practice system is a small orders-and-invoices API called OrderDesk with defects planted on purpose; issue 101 is "the invoice says $175, the order says $150".

Run the offline tests and the evaluation:

```bash
python -m pytest -q
```

```bash
python -m assistant eval
```

## 3. Run it with Claude

If the Claude Code CLI is installed and logged in (`claude --version`), tell the agent to use it as the model:

```bash
LLM_PROVIDER=claude-code python -m assistant investigate 101
```

No API key and no endpoint. Each model call goes through `claude -p`. See [Tutorial 2](Tutorial-2-Claude-Code-as-the-Model.md) for how, and what it costs.

To make this permanent, copy the template and edit it:

```bash
cp .env.example .env
```

Set `LLM_PROVIDER=claude-code` in `.env`. The file is git-ignored.

## 4. Or use an API key instead

Any OpenAI-compatible endpoint works. In `.env`:

```text
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=<your key>
LLM_MODEL=<a model that is good at tool calling>
```

Never paste a key into a chat, an issue or a commit.

## 5. Where to go next

- The course modules are in `study/` (each as Markdown and as a notebook); the map is in the repository README.
- Point the agent at a real GitHub issue: [Tutorial 3](Tutorial-3-Investigate-a-Real-Issue.md).
- Watch Claude build the restaurant: [Tutorial 4](Tutorial-4-The-claude-ready-Pipeline.md).
