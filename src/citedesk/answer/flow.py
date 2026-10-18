"""The answer flow, written as a small LangGraph graph.

    retrieve --> write --> verify --> finish
                   ^          |
                   +--retry---+--> refuse   (when attempts run out)
    retrieve --> refuse                     (when nothing relevant was found)
    write    --> refuse                     (writer says the passages do not answer, or is down)

Each question gets a fresh run with its own state. The graph is compiled without a
checkpointer, so no state is ever shared between questions.
"""

from collections.abc import Callable
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from citedesk.answer.verifier import cited_markers, verify_answer
from citedesk.domain.errors import WriterUnavailableError
from citedesk.domain.models import Answer, Citation, Passage
from citedesk.domain.ports import AnswerWriter

Retrieve = Callable[[str], list[Passage]]

REFUSAL_NOTHING_FOUND = "nothing_relevant_found"
REFUSAL_UNVERIFIED = "could_not_verify_answer"
REFUSAL_NO_ANSWER = "passages_do_not_answer"  # the writer said the passages do not answer it
REFUSAL_MODEL_DOWN = "model_unavailable"


class FlowState(TypedDict, total=False):
    question: str
    corpus_version: int
    passages: list[Passage]
    draft: str
    problems: tuple[str, ...]
    attempts: int
    refusal_reason: str
    answer: Answer


def build_answer_flow(
    retrieve: Retrieve, writer: AnswerWriter, *, max_attempts: int = 2
) -> Callable[[str, int], Answer]:
    """Return a function `ask(question, corpus_version) -> Answer`."""

    def retrieve_node(state: FlowState) -> FlowState:
        return {"passages": retrieve(state["question"]), "attempts": 0}

    def after_retrieve(state: FlowState) -> Literal["write", "refuse"]:
        return "write" if state["passages"] else "refuse"

    def write_node(state: FlowState) -> FlowState:
        attempts = state["attempts"]
        try:
            draft = writer.write(state["question"], state["passages"], strict=attempts > 0)
        except WriterUnavailableError:
            return {"draft": "", "attempts": attempts + 1, "refusal_reason": REFUSAL_MODEL_DOWN}
        if not draft.strip():  # the writer decided the passages do not answer the question
            return {"draft": "", "attempts": attempts + 1, "refusal_reason": REFUSAL_NO_ANSWER}
        return {"draft": draft, "attempts": attempts + 1}

    def after_write(state: FlowState) -> Literal["verify", "refuse"]:
        return "verify" if state["draft"] else "refuse"

    def verify_node(state: FlowState) -> FlowState:
        result = verify_answer(state["draft"], state["passages"])
        return {"problems": result.problems}

    def after_verify(state: FlowState) -> Literal["finish", "write", "refuse"]:
        if not state["problems"]:
            return "finish"
        return "write" if state["attempts"] < max_attempts else "refuse"

    def finish_node(state: FlowState) -> FlowState:
        passages = state["passages"]
        citations = tuple(
            _citation(number, passages[number - 1]) for number in cited_markers(state["draft"])
        )
        return {
            "answer": Answer(
                question=state["question"],
                text=state["draft"],
                citations=citations,
                corpus_version=state["corpus_version"],
            )
        }

    def refuse_node(state: FlowState) -> FlowState:
        default = REFUSAL_UNVERIFIED if state.get("passages") else REFUSAL_NOTHING_FOUND
        reason = state.get("refusal_reason", default)
        return {
            "answer": Answer(
                question=state["question"],
                text="",
                refused=True,
                refusal_reason=reason,
                corpus_version=state["corpus_version"],
            )
        }

    graph = StateGraph(FlowState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("write", write_node)
    graph.add_node("verify", verify_node)
    graph.add_node("finish", finish_node)
    graph.add_node("refuse", refuse_node)
    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges("retrieve", after_retrieve)
    graph.add_conditional_edges("write", after_write)
    graph.add_conditional_edges("verify", after_verify)
    graph.add_edge("finish", END)
    graph.add_edge("refuse", END)
    compiled: Any = graph.compile()

    def ask(question: str, corpus_version: int) -> Answer:
        final_state: FlowState = compiled.invoke(
            {"question": question, "corpus_version": corpus_version}
        )
        return final_state["answer"]

    return ask


def _citation(number: int, passage: Passage) -> Citation:
    return Citation(
        marker=number,
        chunk_id=passage.chunk_id,
        document_title=passage.document_title,
        section_path=passage.section_path,
        quote=passage.text,
    )
