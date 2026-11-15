# Glossary

Short definitions in the sense used in this course. Longer notes: [concepts.md](concepts.md).

| Term | Meaning |
|---|---|
| **Agent** | A model in a loop with tools, deciding its own next step until the task is done. |
| **Agent loop** | Ask the model, run the tools it requested, return the results, repeat. |
| **Approval gate** | A point where the system waits for a person to approve, edit or reject an action. |
| **Approver** | The function the harness calls before running a tool marked as a write. |
| **BM25** | A keyword ranking formula: rare query terms count more, repetition counts less, length is normalised. |
| **Checkpoint** | A saved copy of a workflow's state after a node, used to resume. |
| **Chunk** | A passage of a document: the unit that retrieval ranks and returns. |
| **Clearing** | Replacing old tool results in the model's view with one-line stubs. |
| **Compaction** | Replacing older conversation with a summary written by a model. |
| **Connector** | The tools and authentication for one external system. |
| **Context (window)** | Everything sent to the model in one call; also the maximum size of that. |
| **Context rot** | Lower quality of answers as the context fills with irrelevant or stale text. |
| **Cosine similarity** | How closely two vectors point in the same direction; the usual measure for embeddings. |
| **Embedding** | A list of numbers representing a text, such that similar meanings give similar vectors. |
| **Errors as data** | Returning a failure to the model as a readable tool result instead of raising an exception. |
| **Evaluation case** | A task together with what a correct result must contain. |
| **Evidence grounding** | Requiring that every quoted piece of evidence appears in a tool result of the run. |
| **Execution state** | What a task knows so far, saved outside the context so that it survives a restart. |
| **Final check** | Code that accepts or rejects the agent's final answer before the run ends. |
| **Finish reason** | Why the model stopped: `stop`, `length` (cut off), `tool_calls`. |
| **Grader** | A function that scores one aspect of a run against a case's expectations. |
| **Guardrail** | A control that holds whatever the model outputs. |
| **Hallucination** | A plausible statement that is not supported by anything the model was given. |
| **Harness** | The program around the model: tools, validation, permissions, limits, context, recording. |
| **Human-in-the-loop** | A person decides before a consequential action happens. |
| **Hybrid search** | Keyword and vector rankings merged into one. |
| **Idempotent** | Safe to do twice: the second time changes nothing. |
| **Interrupt** | LangGraph's way of pausing a node until a person supplies a value. |
| **JSON Schema** | A standard description of the shape of a JSON value; used for tool arguments and outputs. |
| **JSONL** | A file with one JSON object per line; used for traces. |
| **Ledger** | The harness's own record of every tool call and its result. |
| **LLM** | Large language model: a stateless function from text to text. |
| **Long-term memory** | Lessons kept across tasks. |
| **MCP** | Model Context Protocol: a standard for offering tools from a separate server to any agent. |
| **Model judge** | A model call used to grade another model's output against a reference. |
| **Node** | One step of a workflow: a function from state to a state update. |
| **OpenAI-compatible** | An endpoint that accepts the chat completions request format, whichever model is behind it. |
| **Orchestration** | Deciding in code which step runs next and what survives a failure. |
| **Pass rate** | The share of repeated runs of a case that pass; the unit of evaluation for a non-deterministic agent. |
| **Progressive disclosure** | A cheap index up front, detail only on request (skills, search then read). |
| **Prompt caching** | A provider feature that charges less for the unchanged beginning of a prompt. |
| **Prompt injection** | Text in the model's input that tries to act as instructions. *Indirect*: arriving through data the agent reads. |
| **RAG** | Retrieval-augmented generation: search first, then give the model only the matching passages. |
| **Recall@k** | The share of queries for which a wanted document is among the top k results. |
| **Redaction** | Masking sensitive values (emails, keys) in text before it leaves a tool. |
| **Repair loop** | Sending validation errors back to the model for a corrected answer, a bounded number of times. |
| **Reciprocal rank fusion** | Merging ranked lists by summing `1 / (constant + rank)` for each item. |
| **Skill** | A reusable procedure with a short description, loaded into the context when a task needs it. |
| **Stand-in** | This course's scripted replacement for the model, so that labs run without a key. |
| **Stop reason** | The harness's named reason for ending a run: `submitted`, `max_steps`, `model_error`, ... |
| **Structured output** | A model answer constrained to and validated against a schema. |
| **Sub-agent** | An agent started by another agent or by code for part of a task, with its own context. |
| **System prompt** | The developer's instructions at the start of the messages. |
| **Temperature** | How much randomness is used when picking each next token. |
| **Token** | A piece of a word; the unit of model input, output and price. Roughly four characters. |
| **Tool** | A function offered to the model: name, description, argument schema, implementation. |
| **Tool calling** | The API convention by which a model requests a tool and receives its result. |
| **Trace** | The ordered events of one run. |
| **Untrusted content** | Text the developers did not write: issues, files, documents, tool results. Data, never instructions. |
| **Vector index** | Stored embeddings with a way to find those nearest to a query. |
| **Workflow** | A fixed graph of steps with shared state and checkpoints. |
