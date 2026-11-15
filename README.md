# Building Practical AI Agents: GitHub Engineering Assistant

**A hands-on self-study course for Software Engineers, Database Administrators and QA Engineers.**
16 hours of core material in six modules, plus a 4-hour optional extension. Python, with any OpenAI-compatible
model endpoint, or no model at all.

You build an AI agent **from scratch**: the loop, the tools, the guards, the memory, the retrieval, the
evaluation. No agent framework hides the machinery. By the end you can explain how agents such as Codex and
Claude Code work inside, and you have an assistant that investigates GitHub issues and reviews pull requests for
your own discipline.

```mermaid
flowchart LR
    I([GitHub issue or PR]) --> A
    subgraph A["THE ASSISTANT you build"]
        direction TB
        L["Agent loop + harness<br/>limits · validation · approvals"] --- T["Tools<br/>GitHub · code · database · CI · logs"]
        L --- C["Context, plan, notes<br/>resumable state"]
        L --- K["Retrieval<br/>incidents · runbooks · standards"]
    end
    A --> F["Findings with checked evidence<br/>root cause · fix · regression tests"]
    F --> H{{"Human approval"}} --> P([Comment on GitHub])
    E["Traces + evaluation against known answers"] -.measures.-> A
```

## Start here

1. **[docs/setup.md](docs/setup.md)**: install (15 to 20 minutes), open the notebooks, optionally connect a model.
2. Work through the modules **in order**. Each exists twice with the same content: a Markdown file to read
   anywhere and a Jupyter notebook to run.
3. Keep **[docs/concepts.md](docs/concepts.md)** open: one page of concept notes for all fourteen concepts.

Stuck: [docs/troubleshooting.md](docs/troubleshooting.md). Unfamiliar term: [docs/glossary.md](docs/glossary.md).

**No API key?** Every lab runs without one. A scripted stand-in plays the part of the model, and everything
around it (tools, harness, guards, state, retrieval, MCP, workflow, evaluation) is real. Run the labs again with
a model when you have one; that is where the behaviour gets interesting.

## Course map

| Module | Time | You build | Concepts |
|---|---|---|---|
| [1. A basic agent](study/module_1_basic_agent.md) · [notebook](study/module_1_basic_agent.ipynb) | 2 h | A prompt and schema that turn an issue into an honest first analysis | LLMs, prompt engineering |
| [2. Tools and the harness](study/module_2_tools_and_harness.md) · [notebook](study/module_2_tools_and_harness.ipynb) | 3 h | The agent loop by hand; twelve guarded read-only tools; checked findings | Tool calling, agent loop and harness |
| [3. Context, memory and RAG](study/module_3_context_memory_rag.md) · [notebook](study/module_3_context_memory_rag.ipynb) | 3 h | A context budget, a plan, resumable state, retrieval you measured | Context engineering, planning, memory, RAG |
| [4. MCP and orchestration](study/module_4_mcp_and_orchestration.md) · [notebook](study/module_4_mcp_and_orchestration.ipynb) | 3 h | An MCP server and client; a LangGraph workflow with an approval gate | Connectors and MCP, workflows, human-in-the-loop |
| [5. Evaluation and reliability](study/module_5_evaluation_and_reliability.md) · [notebook](study/module_5_evaluation_and_reliability.ipynb) | 3 h | Traces, an evaluation suite, injected failures, attacks as tests | Observability, evaluation, security |
| [6. Final project](study/module_6_final_project.md) · [notebook](study/module_6_final_project.ipynb) | 2 h | A demonstration for your discipline | Everything, applied |
| [7. Optional extensions](study/module_7_optional_extensions.md) · [notebook](study/module_7_optional_extensions.ipynb) | 4 h | Skills, long-term memory, multi-agent experiments | Skills, memory, multi-agent |

## The practice system

Everything is investigated on one small system, **OrderDesk** (`workshop/`): a REST API for orders, invoices and
payments with a SQLite database, a test suite, six GitHub issues, four pull requests, a slow-query log, execution
plans, CI results and seventeen historical documents. It contains defects on purpose, and the expected findings
are written down so that the assistant can be evaluated. All customer data is synthetic and every tool is
read-only.

| Case | What is reported | Mostly for |
|---|---|---|
| Issue #101 | Order total $150, invoice $175 | Everyone (the running example) |
| Issue #102 | An endpoint became slow after a release | DBA |
| Issue #103 | A total is one cent too low; the tests are green | QA |
| Issue #104 | The newest orders are missing from page 1 | SWE |
| Issue #105 | A vague report with instructions planted for AI assistants | Security lab |
| Issue #106 | "I was charged twice" (nothing is wrong) | Everyone (the false-positive case) |
| PR #201 to #204 | A partial fix, a risky migration, a feature with thin tests, an injectable endpoint | All roles |

## For each role

| | Software engineer | Database administrator | QA engineer |
|---|---|---|---|
| Your cases | #104, PR #204 | #102, PR #202 | #103, PR #203 |
| Every module has | An SWE exercise | A DBA exercise | A QA exercise |
| Run from a terminal | `python -m assistant investigate 104 --role swe` | `python -m assistant investigate 102 --role dba` | `python -m assistant review 203 --role qa` |
| Final project | Root cause in code; review a fix | Slow query diagnosis; migration review | Missing tests; regression coverage |

Nobody needs to be an expert in another participant's field. The cross-discipline cases (#101, PR #201) are
there so that you learn from each other.

## Studying as a group

- **Pair across disciplines** for the labs and swap who types each module.
- After each module, hold a **15-minute demo**: one person shows a trace from their role's case and the others
  say what they would have checked differently.
- Before reading a ✅ Checkpoint, **predict the output**. Wrong predictions are where the learning is.
- Collect questions for the group in a shared file; answer them from the code, which is small enough to read.
- One person with a model key can project a live run while the others compare it with the stand-in.

## What is in this folder

```text
github-engineering-assistant/
├── README.md            this file
├── requirements.txt     Python packages (no agent framework, no model SDK)
├── .env.example         model settings template (copy to .env, which is git-ignored)
├── docs/                setup, concept notes, glossary, troubleshooting, using a real GitHub repository
├── study/               the modules: <module>.md (source) and <module>.ipynb (generated from it)
├── assistant/           the agent, plain Python, growing module by module
│   ├── llm.py               M1  the model client (one HTTP endpoint)
│   ├── analysis.py          M1  prompt, schema, repair loop
│   ├── tools.py, guards.py  M2  tools and the guards inside them
│   ├── harness.py           M2  the loop, the checks, the limits, the ledger
│   ├── findings.py          M2  the result schema and the evidence check
│   ├── context.py, state.py M3  context manager; resumable investigation state
│   ├── retrieval.py         M3  chunking, BM25, vectors, hybrid, recall
│   ├── mcp_server.py, mcp_client.py   M4
│   ├── workflow.py          M4  the LangGraph workflow (the only LangGraph import)
│   ├── tracing.py, evals.py, reliability.py   M5
│   ├── skills.py, memory.py, multi.py         M7
│   ├── app.py               puts the parts together (build_assistant)
│   └── __main__.py          command line: python -m assistant investigate | review | eval
├── skills/              three reusable procedures (SKILL.md files)
├── lab/                 learning support: the scripted stand-in, its scripts, fault injection, samples
├── workshop/            the practice system
│   ├── repo/                the OrderDesk application, with defects
│   ├── github/              issues, pull requests and commits as files
│   ├── ops/                 slow-query log, execution plans, CI runs
│   ├── knowledge/           incidents, runbooks, standards
│   ├── expected/            evaluation cases and labelled retrieval queries (do not show these to the agent)
│   └── seed.py              builds orderdesk.db deterministically
├── tests/               80 offline tests (no model, no internet): python -m pytest
└── tools/               build_notebooks.py (study/*.md → *.ipynb), run_notebooks.py
```

## Run it

From this folder, with the virtual environment active:

```bash
python -m pytest -q
```

```bash
python -m assistant investigate 101
```

```bash
python -m assistant review 204 --role swe
```

```bash
python -m assistant eval
```

Traces go to `out/traces/`, drafted comments to `out/outbox/`. Nothing is ever sent to GitHub unless you
configure a live repository and approve the comment ([docs/live-github.md](docs/live-github.md)).

## For maintainers

- Edit `study/*.md`, then run `python tools/build_notebooks.py`. With `--check` it fails if a notebook is stale.
  Notebooks are committed without outputs.
- `python tools/run_notebooks.py` executes every notebook top to bottom and reports the first failing cell.
- The checkpoints quote numbers from the stand-in runs. If you change a script in `lab/scripts.py`, a tool's
  output format or the seed data, rerun the notebooks and update the checkpoints.
- `workshop/seed.py` is deterministic. `tests/test_workshop.py` fails if the data no longer matches the expected
  findings.

---

**Guiding principle.** We are not learning AI agent frameworks for their own sake. We are learning how agents
work by building practical automation that SWE, DBA and QA professionals can adapt to their workplaces.
