import json

from assistant.app import build_assistant, issue_task
from assistant.context import ContextManager, conversation_tokens
from assistant.harness import Limits
from assistant.retrieval import BM25Index, Chunk, Retriever, chunk_document, load_documents, recall_at_k, reciprocal_rank_fusion
from assistant.state import InvestigationState
from lab.scripts import SCRIPTS
from lab.standin import ScriptedModel


def test_clearing_keeps_the_run_working_and_the_record_complete(run_script):
    result, assistant = run_script("issue-101", context_tokens=3000)
    assert any(entry["cleared"] for entry in assistant.agent.context.history)
    assert result.stop_reason == "submitted"
    assert not any(str(message.get("content")).startswith("[cleared") for message in result.messages)


def test_view_is_smaller_keeps_pairing_and_shows_notes(run_script):
    result, assistant = run_script("issue-102", context_tokens=None)
    plain = ContextManager(max_tokens=2000, keep_recent=2).prepare(result.messages)
    assert conversation_tokens(plain) < 0.7 * conversation_tokens(result.messages)
    assert len(plain) == len(result.messages)
    assert [m.get("tool_call_id") for m in plain] == [m.get("tool_call_id") for m in result.messages]
    assert "[cleared to save context: get_slow_queries(top=5)" in json.dumps(plain)
    assert plain[-1] == result.messages[-1] and plain[-3]["content"] == result.messages[-3]["content"]
    with_notes = ContextManager(max_tokens=2000, keep_recent=2, state=assistant.state).prepare(result.messages)
    assert "<investigation_state>" in with_notes[0]["content"] and "<investigation_state>" not in result.messages[0]["content"]


def test_interrupted_run_resumes_from_saved_state(workspace, tmp_path):
    path, task = tmp_path / "state.json", issue_task(101)
    first = build_assistant(ScriptedModel(SCRIPTS["issue-101"]), workspace=workspace, task=task, state_path=path,
                            limits=Limits(max_steps=6))
    interrupted = first.agent.run(task)
    assert interrupted.stop_reason == "max_steps" and path.exists()

    saved = InvestigationState.load(path)
    assert saved.facts and saved.plan and any("get_issue" in signature for signature in saved.calls_done)

    second = build_assistant(ScriptedModel(SCRIPTS["issue-101"]), workspace=workspace, task=task, state_path=path,
                             resume=True)
    resumed = second.agent.run(second.state.resume_prompt())
    assert resumed.stop_reason == "submitted"
    repeated = {record.signature for record in resumed.ledger} & set(saved.calls_done)
    assert not {s for s in repeated if not s.startswith(("update_plan", "record_note"))}
    assert resumed.tool_calls < 23


def test_bm25_prefers_rare_terms():
    chunks = [Chunk("a", 0, "index index index on the orders table"), Chunk("b", 0, "the orders table"),
              Chunk("c", 0, "orders and invoices")]
    assert BM25Index(chunks).search("index orders", 1)[0][0] == 0
    assert reciprocal_rank_fusion([[1, 2, 3], [2, 1, 9]])[0][0] in (1, 2)


def test_chunks_carry_the_title(workspace):
    documents = load_documents(workspace.knowledge)
    assert len(documents) == 17
    assert all(chunk.text.startswith(documents[0].title) for chunk in chunk_document(documents[0]))


def test_retrieval_quality_does_not_regress(workspace):
    labelled = json.loads((workspace.expected / "retrieval_queries.json").read_text())["queries"]
    same = [q for q in labelled if q["style"] == "same words"]
    assert recall_at_k(Retriever(workspace.knowledge, "keyword"), same, 3)["recall"] == 1.0
    hybrid = recall_at_k(Retriever(workspace.knowledge, "hybrid"), [q for q in labelled if q["style"] != "no shared words"], 3)
    assert hybrid["recall"] >= 0.9
