# Setup Guide

Everything you need before Module 1. It takes 15 to 20 minutes the first time. Steps 1 to 4 are required. Step 5
(a model) can wait: **every lab runs without one.**

When a step has a **✅ Check**, do not move on until you see what it describes. If you are stuck, see
[troubleshooting.md](troubleshooting.md).

---

## 1. Get the code

```bash
git clone https://github.com/thehungrycoder/ai-learning-agent.git
```

```bash
cd ai-learning-agent/github-engineering-assistant
```

✅ **Check:** `ls` shows `README.md`, `assistant`, `docs`, `lab`, `study`, `tests`, `workshop`.

The repository also contains `offer-scout/`, an earlier, archived course. The two are independent; each has its
own virtual environment and requirements.

## 2. Python 3.11 or newer

```bash
python3 --version
```

✅ **Check:** `Python 3.11.x` or higher. If it is older or missing:

| System | How |
|---|---|
| macOS | `brew install python@3.12`, or the installer from [python.org](https://www.python.org/downloads/) |
| Windows | Installer from [python.org](https://www.python.org/downloads/). Tick **"Add python.exe to PATH"**. Use `py -3.12` instead of `python3` below. |
| Ubuntu/Debian | `sudo apt install python3 python3-venv python3-pip` |

## 3. Virtual environment and packages

```bash
python3 -m venv .venv
```

Activate it. Do this **every time you open a new terminal**:

```bash
source .venv/bin/activate
```

On Windows (PowerShell or cmd):

```bash
.venv\Scripts\activate
```

✅ **Check:** your prompt starts with `(.venv)`.

```bash
pip install --upgrade pip
```

```bash
pip install -r requirements.txt
```

✅ **Check:** the last line says `Successfully installed ...` with no red `ERROR` lines.

Run the offline tests. They build the practice database on first use.

```bash
python -m pytest -q
```

✅ **Check:** `80 passed` (the number may grow). This proves that the tools, the harness, the guards, retrieval,
the MCP server and the workflow all work on your machine, with no model and no internet.

Create your settings file (it stays on your machine; it is git-ignored):

```bash
cp .env.example .env
```

On Windows: `copy .env.example .env`.

## 4. Open the notebooks

Pick **one** option.

### Option A: JupyterLab

```bash
jupyter lab
```

In the left panel open `study/module_1_basic_agent.ipynb`.

✅ **Check:** the first code cell (run it with **Shift+Enter**) prints `LLM ready ...` or `LLM NOT ready ...`.
Both are fine.

Useful: **Kernel → Restart Kernel and Run All Cells** reruns everything from the top. It cures most odd errors.

### Option B: VS Code

1. Install the **Python** and **Jupyter** extensions.
2. Open the `github-engineering-assistant` folder (*File → Open Folder*).
3. Open `study/module_1_basic_agent.ipynb`.
4. **Select Kernel** (top right) → *Python Environments* → the one in `.venv`.

✅ **Check:** the kernel picker shows `.venv`, and the first cell runs.

### Option C: No Jupyter

Each module's `.md` file has exactly the same content. Read it on GitHub or in any Markdown viewer and run the
```` ```python ```` blocks **in order** in one Python session started from this folder:

```bash
python
```

Blocks inside a collapsed ▶ note are for reading, not for running.

## 5. Connect a model (optional, any time)

The course talks to one HTTP endpoint: `POST {LLM_BASE_URL}/chat/completions`, the OpenAI-compatible chat API.
Almost every provider and gateway offers it.

Edit `.env`:

```text
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=your key
LLM_MODEL=the model id exactly as your endpoint lists it
```

| Endpoint | `LLM_BASE_URL` | Notes |
|---|---|---|
| OpenRouter | `https://openrouter.ai/api/v1` | One key, many models. Copy the id from the model page. |
| A LiteLLM proxy or company gateway | `http://your-host:4000/v1` | Ask your platform team for the URL and the model names. |
| OpenAI | `https://api.openai.com/v1` | |
| Ollama on your laptop | `http://localhost:11434/v1` | No key needed. Use a model that supports tool calling. |

**If you still have the `.env` from the Offer Scout course**, copy its `LLM_BASE_URL`, `LLM_API_KEY` and
`LLM_MODEL` lines: the names are the same.

**Choosing a model.** From Module 2 on the model must be good at **tool calling**: it makes ten to twenty tool
calls per investigation and must produce valid JSON arguments. Current mid-size and large models from the major
providers do this well; very small or older models loop, invent tool names or stop early (which is instructive,
once). Start with the model your team already uses.

✅ **Check:** restart the kernel and run the first cell of any module. It prints
`LLM ready: model=... endpoint=... (configured)`.

Then confirm a real round trip from a terminal:

```bash
python -m assistant investigate 106
```

✅ **Check:** a trace of model and tool steps, then findings. With a model the path differs from the stand-in's.

| Optional setting | What for |
|---|---|
| `LLM_TEMPERATURE=0` | More repeatable runs, **if** your model accepts the parameter. Remove it if you get HTTP 400. |
| `LLM_MAX_TOKENS=4000` | Caps one reply. Raise it if answers are cut off (`finish_reason: length`). |
| `LLM_FAST_MODEL=` | A cheaper model for small jobs (the model judge in Module 5). |
| `LLM_PROVIDER=standin` | Forces the scripted stand-in although a key is set. Useful for comparing. |
| `LLM_PROVIDER=claude-code` | Uses the Claude Code CLI (`claude -p`) as the model, so no API key or endpoint is needed. `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` are ignored; pick a model with `CLAUDE_CODE_MODEL` (an alias such as `sonnet`, empty for the CLI default). Calls draw on your Claude plan, and each one re-sends the whole conversation. |
| `EMBED_MODEL=` | A real embedding model for Module 3 (`POST {base}/embeddings`). |
| `PRICE_INPUT_PER_MTOK=`, `PRICE_OUTPUT_PER_MTOK=` | Your model's prices, for the cost figures in Module 5. |

### What it costs

One investigation is roughly 50,000 to 150,000 input tokens and a few thousand output tokens, depending on the
model's habits. The full evaluation suite (ten cases) is about ten times that. Multiply by your model's prices
before running the suite in a loop. The stand-in is free.

## 6. Know your way around

| I want to | Go to |
|---|---|
| Read a concept in two minutes | [concepts.md](concepts.md) |
| See what the assistant is made of | `assistant/app.py`, then `assistant/harness.py` |
| Look at the practice system | `workshop/repo/README.md`, `workshop/github/issues/` |
| See what the stand-in "says" | `lab/scripts.py` |
| Reset everything | Delete `out/` and `workshop/orderdesk.db`; both are rebuilt on demand |
