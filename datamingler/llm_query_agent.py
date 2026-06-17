from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Callable, Literal, TypedDict

from .graph import DVMGraph
from .local_query_planner import plan_natural_language
from .xmlio import parse_query_text

Provider = Literal["openai", "anthropic"]


@dataclass(frozen=True)
class AgentStep:
    name: str
    status: str
    detail: str
    data: dict[str, Any] | None = None


@dataclass(frozen=True)
class AgentQuery:
    title: str
    query: str
    result: str = ""
    error: str = ""


@dataclass(frozen=True)
class AgentResponse:
    answer: str
    queries: list[AgentQuery]
    steps: list[AgentStep]
    provider: Provider
    model: str


class AgentState(TypedDict, total=False):
    prompt: str
    graph: DVMGraph
    schema: dict[str, Any]
    provider: Provider
    model: str
    evaluate_query: Callable[[str], str]
    steps: list[AgentStep]
    queries: list[AgentQuery]
    answer: str
    history: list[dict[str, str]]


def run_query_agent(
    prompt: str,
    graph: DVMGraph,
    *,
    provider: Provider,
    model: str,
    evaluate_query: Callable[[str], str],
    history: list[dict[str, str]] | None = None,
) -> AgentResponse:
    """Run an LLM query agent over the DVM graph.

    The orchestration uses LangGraph when the optional LLM dependencies are
    installed. The LLM is called through LangChain provider integrations, and it
    can generate QDVM, execute it through the supplied evaluator, observe output,
    and then answer the user with a visible trace.
    """
    _require_langchain(provider)

    state: AgentState = {
        "prompt": prompt,
        "graph": graph,
        "provider": provider,
        "model": model,
        "evaluate_query": evaluate_query,
        "steps": [],
        "queries": [],
        "answer": "",
        "history": history or [],
    }

    try:
        from langgraph.graph import END, START, StateGraph

        workflow = StateGraph(AgentState)
        workflow.add_node("inspect_schema", _inspect_schema)
        workflow.add_node("plan_queries", _plan_queries)
        workflow.add_node("execute_queries", _execute_queries)
        workflow.add_node("summarize", _summarize)
        workflow.add_edge(START, "inspect_schema")
        workflow.add_edge("inspect_schema", "plan_queries")
        workflow.add_edge("plan_queries", "execute_queries")
        workflow.add_edge("execute_queries", "summarize")
        workflow.add_edge("summarize", END)
        final_state = workflow.compile().invoke(state)
    except ImportError as exc:
        raise RuntimeError("LLM query agent requires optional dependency: pip install datamingler[llm]") from exc

    return AgentResponse(
        answer=str(final_state.get("answer", "")),
        queries=list(final_state.get("queries", [])),
        steps=list(final_state.get("steps", [])),
        provider=provider,
        model=model,
    )


def response_to_dict(response: AgentResponse) -> dict[str, Any]:
    return {
        "answer": response.answer,
        "provider": response.provider,
        "model": response.model,
        "queries": [asdict(query) for query in response.queries],
        "steps": [asdict(step) for step in response.steps],
    }


def _inspect_schema(state: AgentState) -> AgentState:
    graph = state["graph"]
    schema = {
        "nodes": sorted(graph.nodes),
        "edges": [
            {
                "head": edge.head_name,
                "tail": edge.tail_name,
                "datasource": edge.datasource,
                "selected": edge.selected,
                "query": edge.query,
            }
            for edge in graph.edges
        ],
    }
    return {
        **state,
        "schema": schema,
        "steps": [
            *state.get("steps", []),
            AgentStep(
                "Inspect schema",
                "ok",
                f"Loaded {len(schema['nodes'])} nodes and {len(schema['edges'])} DVM edges.",
                {"nodes": schema["nodes"], "edges": schema["edges"][:20]},
            ),
        ],
    }


def _plan_queries(state: AgentState) -> AgentState:
    llm = _chat_model(state["provider"], state["model"])
    schema = state["schema"]
    prompt = state["prompt"]
    system = (
        "You are a DataMingler QDVM query agent. Generate one or more valid QDVM queries. "
        "Use only DVM node names and edges from the schema. Return JSON only with this shape: "
        '{"queries":[{"title":"short title","query":"QDVM text"}]}. '
        "QDVM syntax: define <label> on <node>: lines with compute <label> on <node> "
        "transformedby '<chain>', output comma-separated child labels, where expression. "
        "Use aggregate:any for ordinary fields. Use map:python,,len($LABEL$);aggregate:sum for requested text length."
    )
    user = (
        f"Conversation history:\n{json.dumps(state.get('history', []), indent=2)}\n\n"
        f"Schema:\n{json.dumps(schema, indent=2)}\n\n"
        f"User request:\n{prompt}"
    )
    content = _invoke_llm(llm, system, user)
    parsed = _parse_llm_queries(content)

    if not parsed:
        generated = plan_natural_language(prompt, state["graph"])
        parsed = [{"title": item.title, "query": item.query} for item in generated]

    queries = []
    validation_errors = []
    for index, item in enumerate(parsed, start=1):
        title = str(item.get("title") or f"Query {index}")
        query = str(item.get("query") or "")
        try:
            parse_query_text(query)
            queries.append(AgentQuery(title=title, query=query))
        except Exception as exc:
            validation_errors.append({"title": title, "error": str(exc), "query": query})

    if not queries:
        generated = plan_natural_language(prompt, state["graph"])
        queries = [AgentQuery(title=item.title, query=item.query) for item in generated]

    return {
        **state,
        "queries": queries,
        "steps": [
            *state.get("steps", []),
            AgentStep(
                "Plan queries",
                "ok" if queries else "error",
                f"Generated {len(queries)} executable QDVM query candidate(s).",
                {"raw_model_output": content, "validation_errors": validation_errors},
            ),
        ],
    }


def _execute_queries(state: AgentState) -> AgentState:
    evaluate_query = state["evaluate_query"]
    executed = []
    for query in state.get("queries", []):
        try:
            result = evaluate_query(query.query)
            executed.append(AgentQuery(title=query.title, query=query.query, result=result))
        except Exception as exc:
            executed.append(AgentQuery(title=query.title, query=query.query, error=str(exc)))

    return {
        **state,
        "queries": executed,
        "steps": [
            *state.get("steps", []),
            AgentStep(
                "Run queries",
                "ok",
                f"Ran {len(executed)} query candidate(s) and captured outputs/errors.",
                {
                    "queries": [
                        {
                            "title": item.title,
                            "ok": not bool(item.error),
                            "result_preview": item.result[:1000],
                            "error": item.error,
                        }
                        for item in executed
                    ]
                },
            ),
        ],
    }


def _summarize(state: AgentState) -> AgentState:
    llm = _chat_model(state["provider"], state["model"])
    observations = [
        {
            "title": query.title,
            "query": query.query,
            "result": query.result[:4000],
            "error": query.error,
        }
        for query in state.get("queries", [])
    ]
    system = "You are a concise data assistant. Explain what you did and summarize the query result."
    user = (
        f"Conversation history:\n{json.dumps(state.get('history', []), indent=2)}\n\n"
        f"User request:\n{state['prompt']}\n\n"
        f"Executed QDVM observations:\n{json.dumps(observations, indent=2)}"
    )
    answer = _invoke_llm(llm, system, user)
    return {
        **state,
        "answer": answer,
        "steps": [
            *state.get("steps", []),
            AgentStep("Summarize", "ok", "LLM reviewed query output and produced the final answer."),
        ],
    }


def _require_langchain(provider: Provider) -> None:
    missing = []
    try:
        import langgraph  # noqa: F401
    except ImportError:
        missing.append("langgraph")
    try:
        import langchain_core  # noqa: F401
    except ImportError:
        missing.append("langchain-core")
    if provider == "openai":
        try:
            import langchain_openai  # noqa: F401
        except ImportError:
            missing.append("langchain-openai")
    elif provider == "anthropic":
        try:
            import langchain_anthropic  # noqa: F401
        except ImportError:
            missing.append("langchain-anthropic")
    else:
        raise ValueError("provider must be 'openai' or 'anthropic'")
    if missing:
        raise RuntimeError(f"LLM query agent requires optional dependencies: {', '.join(missing)}")


def _chat_model(provider: Provider, model: str) -> Any:
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, temperature=0)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, temperature=0)
    raise ValueError("provider must be 'openai' or 'anthropic'")


def _invoke_llm(llm: Any, system: str, user: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    content = getattr(response, "content", response)
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(content)


def _parse_llm_queries(content: str) -> list[dict[str, Any]]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    queries = data.get("queries") if isinstance(data, dict) else None
    if not isinstance(queries, list):
        return []
    return [item for item in queries if isinstance(item, dict)]
