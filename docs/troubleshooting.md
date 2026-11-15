# Troubleshooting

Find the symptom, apply the fix. If it is not here: *Kernel → Restart Kernel and Run All Cells*, then ask the group.

## Setup and notebooks

| Symptom | Cause and fix |
|---|---|
| `ModuleNotFoundError: No module named 'assistant'` | The first cell of the module was not run, or Jupyter was started outside the course folder. Run the first cell; start Jupyter from `github-engineering-assistant/`. |
| `ModuleNotFoundError: No module named 'httpx'` (or `pydantic`, `dotenv`) | The virtual environment is not active, or the notebook uses another kernel. Activate `.venv`; in VS Code choose the `.venv` kernel. |
| `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`, or an error mentioning `MCPServer` | An older `mcp` package (1.x) is installed. This course uses the 2.x API: `pip install -r requirements.txt` again. |
| `FileNotFoundError: Start Jupyter (or Python) from inside the course folder.` | The working directory is outside the repository. `cd` into the course folder and restart. |
| A cell fails with `NameError` | A previous cell was skipped. Restart and run all cells from the top. |
| Numbers in a ✅ Checkpoint differ slightly | Checkpoints marked "(stand-in)" are exact for the scripted runs. With a live model they are examples of the shape, not values to match. |
| `sqlite3.OperationalError: unable to open database file` | `workshop/orderdesk.db` is missing and could not be built. Run `python workshop/seed.py` and read its error. |
| The diagrams show as code | Your viewer does not render Mermaid. Open the ▶ text version under each diagram, or view the file on GitHub. |
| Tests fail right after `git pull` | Delete `workshop/orderdesk.db` and `out/`, then run `python -m pytest -q` again. |

## Model calls

| Symptom | Cause and fix |
|---|---|
| `LLM NOT ready: ... (set LLM_MODEL in .env)` | `.env` is missing, in the wrong folder, or incomplete. It must be `github-engineering-assistant/.env`. Restart the kernel after editing it. |
| `ModelError: auth: HTTP 401` | Wrong or expired key, or a key for a different endpoint than `LLM_BASE_URL`. |
| `ModelError: not_found: HTTP 404` | The model id does not exist at this endpoint, or `LLM_BASE_URL` lacks the `/v1` part. Copy the id from the endpoint's model list. |
| `ModelError: bad_request: HTTP 400` mentioning `temperature` | Your model rejects the parameter. Remove `LLM_TEMPERATURE` from `.env`. |
| HTTP 400 mentioning `tools` or `tool_choice` | The model or gateway does not support tool calling. Choose another model. |
| HTTP 400 mentioning `max_tokens` | Some endpoints want `max_completion_tokens`. Remove `LLM_MAX_TOKENS` and set `LLM_EXTRA_BODY={"max_completion_tokens": 4000}`. |
| `ModelError: unavailable: gave up after 4 attempts` | Rate limit or outage. Wait and rerun; check your provider's status and quota. |
| Answers are cut off; JSON does not parse | `finish_reason` is `length`. Raise `LLM_MAX_TOKENS`. |
| Everything is very slow | Reasoning-heavy models can take a minute per step. Use a faster model for the labs, or `LLM_PROVIDER=standin` while you study the mechanics. |

## Agent behaviour (with a live model)

| Symptom | What it tells you, and what to try |
|---|---|
| The run stops with `max_steps` | The model explores too broadly, or loops. Read the trace: where did it stop making progress? Tighten the task, improve a tool description, or use a stronger model. Raising the limit is the last resort. |
| `no_final_answer` | The model answered in prose instead of calling `submit_findings`. Some models need the instruction repeated near the end of the system prompt. |
| `findings_rejected` again and again | The model paraphrases instead of quoting. Check that tool results it needs are still in view (Module 3: context budget too tight?), and that the `quote` field description is being followed. |
| `invalid_arguments` on most calls | The model is weak at structured output. Simplify argument schemas (fewer optional fields), or change model. |
| The model never calls `search_knowledge` or `update_plan` | It may not need them for a simple case. For complex cases, check that the tool descriptions say when to use them. |
| The model repeats a query with small variations | It is not getting what it expects. Look at the tool output it received; often the output format is the problem. |
| Results differ between two runs | Expected. See Module 5 on pass rates. |

## MCP and LangGraph (Module 4)

| Symptom | Cause and fix |
|---|---|
| `RuntimeError: could not connect to the MCP server` | The server process failed to start. Run `python -m assistant.mcp_server` in a terminal to see its error (it waits silently when healthy; stop it with Ctrl+C). |
| The notebook hangs on `McpToolbox(...).start()` | A previous toolbox was not closed and the kernel is confused. Restart the kernel. Always call `toolbox.close()`. |
| `ImportError: cannot import name 'SqliteSaver'` | `pip install langgraph-checkpoint-sqlite` (it is in `requirements.txt`). |
| `invoke` returns immediately with `__interrupt__` | That is the approval gate working. Resume with `Command(resume={...})` and the same `thread_id`. |
| Resuming does nothing or starts over | The `thread_id` differs, or you used `InMemorySaver` in a new process. Checkpoints live in the saver. |

## Still stuck?

1. Read the error's last line, then the first line of your own code in the traceback.
2. Rerun with the stand-in (`LLM_PROVIDER=standin` in `.env`, restart the kernel). If it works there, the problem
   is the model or the endpoint, not the code.
3. Run `python -m pytest -q`. A failing test names the broken part.
4. Write down what you expected, what happened, and the trace file from `out/traces/`. Bring it to the group.
