"""Construction and introspection of the compiled StudyMate StateGraph."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.base import BaseStore

from app.graph.nodes import NODE_NAMES, GraphDeps, build_nodes
from app.graph.state import INTENTS, StudyState

# Conditional edge: router_node returns an intent label; this map turns it into the next node.
ROUTE_MAP: dict[str, str] = {
    "explanation": "explanation_node",
    "quiz": "quiz_node",
    "summarization": "summarization_node",
    "preference": "general_node",
    "general": "general_node",
}

NODE_INFO: dict[str, dict[str, Any]] = {
    "load_memory_node": {
        "title": "Load memory",
        "kind": "memory",
        "description": "Reads the user's structured profile from the LangGraph Store (namespace users/<user_id>/profile) so every later node can personalise. Also resets per-run state.",
        "reads": ["user_id", "messages"],
        "writes": ["student_profile", "retrieved_memory", "current_query", "execution_metadata"],
    },
    "router_node": {
        "title": "Intent router",
        "kind": "router",
        "description": "Classifies the request (forced by the endpoint > keyword rules > LLM classifier > default). Its return value drives the conditional edge.",
        "reads": ["current_query", "forced_intent", "request_payload"],
        "writes": ["intent", "topic", "request_payload"],
    },
    "explanation_node": {
        "title": "Explain",
        "kind": "processing",
        "description": "Builds a personalised system prompt, trims the history to the token budget, and asks the LLM for an explanation.",
        "reads": ["messages", "student_profile", "learning_insights"],
        "writes": ["generated_content", "context_statistics", "learning_insights"],
    },
    "quiz_node": {
        "title": "Generate quiz",
        "kind": "processing",
        "description": "Asks the LLM for a validated JSON multiple-choice quiz (topic, difficulty, number of questions).",
        "reads": ["request_payload", "student_profile", "messages"],
        "writes": ["generated_content", "context_statistics", "learning_insights", "topic"],
    },
    "summarization_node": {
        "title": "Summarise notes",
        "kind": "processing",
        "description": "Produces summary, concepts, revision notes and key terms; long material is chunked (map-reduce) to fit the budget.",
        "reads": ["request_payload", "current_query", "student_profile"],
        "writes": ["generated_content", "context_statistics", "learning_insights", "topic"],
    },
    "general_node": {
        "title": "General / preference",
        "kind": "processing",
        "description": "Handles greetings and acknowledges stated learning preferences (the preference itself is persisted by memory_update_node).",
        "reads": ["messages", "student_profile"],
        "writes": ["generated_content", "context_statistics"],
    },
    "response_node": {
        "title": "Compose response",
        "kind": "response",
        "description": "Converts generated_content to Markdown and appends the assistant message. The messages channel uses the add_messages reducer.",
        "reads": ["generated_content", "intent"],
        "writes": ["messages"],
    },
    "memory_update_node": {
        "title": "Update memory",
        "kind": "memory",
        "description": "Extracts durable learning facts (style, language, subjects, preferences) with a controlled allow-list and writes them to the Store; records studied topics.",
        "reads": ["current_query", "intent", "topic"],
        "writes": ["student_profile", "learning_insights", "execution_metadata"],
    },
}

REDUCERS: dict[str, dict[str, str]] = {
    "messages": {"reducer": "add_messages", "behaviour": "Appends new messages; a message with an existing id replaces it. History is never dropped."},
    "learning_insights": {"reducer": "merge_insights", "behaviour": "Merges by (kind, topic): repeats increment count and union intents instead of replacing the list."},
    "execution_metadata": {"reducer": "merge_execution_metadata", "behaviour": "Appends node trace entries within a run; the first node resets it for each new run."},
}


def route_by_intent(state: StudyState) -> str:
    """Conditional-edge function: the label must be a key of ROUTE_MAP."""
    intent = state.get("intent", "")
    return intent if intent in INTENTS else "explanation"


def build_graph(deps: GraphDeps, checkpointer: BaseCheckpointSaver, store: BaseStore):
    nodes = build_nodes(deps)
    builder = StateGraph(StudyState)
    for name in NODE_NAMES:
        builder.add_node(name, nodes[name])

    builder.add_edge(START, "load_memory_node")
    builder.add_edge("load_memory_node", "router_node")
    builder.add_conditional_edges("router_node", route_by_intent, ROUTE_MAP)
    for processing in ("explanation_node", "quiz_node", "summarization_node", "general_node"):
        builder.add_edge(processing, "response_node")
    builder.add_edge("response_node", "memory_update_node")
    builder.add_edge("memory_update_node", END)
    return builder.compile(checkpointer=checkpointer, store=store, name="studymate")


def describe_graph(graph) -> dict[str, Any]:
    """Serialise the REAL compiled graph (via get_graph()) for the frontend."""
    drawable = graph.get_graph()
    nodes = []
    for node_id, node in drawable.nodes.items():
        info = NODE_INFO.get(node_id, {})
        nodes.append(
            {
                "id": node_id,
                "name": getattr(node, "name", node_id),
                "type": "start" if node_id == "__start__" else "end" if node_id == "__end__" else "node",
                **({"title": info["title"], "kind": info["kind"], "description": info["description"],
                    "reads": info["reads"], "writes": info["writes"]} if info else {}),
            }
        )
    # get_graph() collapses conditional edges that share a target, so rebuild the label from ROUTE_MAP.
    edges = []
    for e in drawable.edges:
        label = None
        if e.conditional:
            label = " / ".join(i for i, target in ROUTE_MAP.items() if target == e.target) or None
        edges.append({"source": e.source, "target": e.target, "conditional": bool(e.conditional), "label": label})
    return {
        "name": "studymate",
        "nodes": nodes,
        "edges": edges,
        "mermaid": drawable.draw_mermaid(),
        "reducers": REDUCERS,
        "state_fields": list(StudyState.__annotations__.keys()),
        "intents": list(INTENTS),
    }
