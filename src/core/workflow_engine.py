from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, Sequence, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph

from .cost_guard import CostGuard


class TaskItem(TypedDict):
    id: str
    title: str
    description: str
    agent: str
    depends_on: list[str]
    success_criteria: str
    status: str


class TaskResult(TypedDict):
    task_id: str
    agent: str
    result: str
    status: str
    error: str | None


class AgentState(TypedDict):
    # basic request metadata
    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_request: str
    session_id: str
    user_id: str | None

    # intent routing
    intent: str
    recommended_workflow: str
    task_complexity: str

    # planning state
    plan: list[TaskItem] | None
    parallel_groups: list[list[str]] | None
    acceptance_criteria: list[str]
    require_approval: bool

    # execution traces
    current_task_index: int
    completed_tasks: Annotated[list[TaskResult], operator.add]
    failed_tasks: Annotated[list[TaskResult], operator.add]

    # loop guard
    loop_active: bool
    loop_iteration: int
    max_loop_iterations: int

    # cost/token guard
    total_cost_usd: float
    total_tokens: int
    max_cost_usd: float
    max_tokens: int

    # retry state
    retry_count: int
    consecutive_failures: int

    # memory placeholders
    past_episodes: list[dict] | None
    user_preferences: dict[str, Any]

    # final outputs
    final_answer: str | None
    workflow_trace: Annotated[list[str], operator.add]


def make_initial_state(
    user_request: str,
    session_id: str,
    *,
    max_loop_iterations: int = 10,
    require_approval: bool = False,
    user_id: str | None = None,
    max_cost_usd: float = 1.0,
    max_tokens: int = 500_000,
) -> AgentState:
    return {
        "messages": [],
        "user_request": user_request,
        "session_id": session_id,
        "user_id": user_id,
        "intent": "",
        "recommended_workflow": "direct",
        "task_complexity": "medium",
        "plan": None,
        "parallel_groups": None,
        "acceptance_criteria": [],
        "require_approval": require_approval,
        "current_task_index": 0,
        "completed_tasks": [],
        "failed_tasks": [],
        "loop_active": True,
        "loop_iteration": 0,
        "max_loop_iterations": max_loop_iterations,
        "total_cost_usd": 0.0,
        "total_tokens": 0,
        "max_cost_usd": max_cost_usd,
        "max_tokens": max_tokens,
        "retry_count": 0,
        "consecutive_failures": 0,
        "past_episodes": None,
        "user_preferences": {},
        "final_answer": None,
        "workflow_trace": [],
    }


def route_by_intent(state: AgentState) -> Literal["planner", "executor", "finalizer"]:
    workflow = state.get("recommended_workflow", "direct")
    if workflow == "plan_execute":
        return "planner"
    if workflow == "ask_clarification":
        return "finalizer"
    return "executor"


def check_execution_result(state: AgentState) -> Literal["reviewer", "executor", "finalizer"]:
    if not state.get("loop_active", True):
        return "finalizer"

    if state.get("total_cost_usd", 0.0) >= state.get("max_cost_usd", 1.0):
        return "finalizer"
    if state.get("total_tokens", 0) >= state.get("max_tokens", 500_000):
        return "finalizer"

    consecutive = state.get("consecutive_failures", 0)
    retry = state.get("retry_count", 0)
    if consecutive >= 3:
        return "reviewer"
    if retry >= 5:
        return "finalizer"

    completed = len(state.get("completed_tasks", []))
    plan = state.get("plan") or []
    total = len(plan)
    if completed >= total and total > 0:
        return "reviewer"
    return "executor"


def check_review_result(state: AgentState) -> Literal["loop_check", "executor", "planner"]:
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    if not last_message:
        return "loop_check"

    content = last_message.content if hasattr(last_message, "content") else ""
    low = content.lower()
    if "replan" in low or "새로운 계획" in low:
        return "planner"
    if "fix" in low or "need_fix" in low:
        return "executor"
    return "loop_check"


def should_continue_loop(state: AgentState) -> Literal["executor", "finalizer"]:
    iteration = state.get("loop_iteration", 0)
    max_iter = state.get("max_loop_iterations", 10)
    if iteration >= max_iter:
        return "finalizer"
    if not state.get("loop_active", True):
        return "finalizer"

    if state.get("total_cost_usd", 0.0) >= state.get("max_cost_usd", 1.0):
        return "finalizer"
    if state.get("total_tokens", 0) >= state.get("max_tokens", 500_000):
        return "finalizer"

    plan = state.get("plan") or []
    completed = len(state.get("completed_tasks", []))
    if completed < len(plan):
        return "executor"
    return "finalizer"


def _extract_token_usage(response: BaseMessage) -> tuple[int, int]:
    """Best-effort token extraction across providers."""
    usage = getattr(response, "usage_metadata", None) or {}
    in_tokens = int(usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0) or 0)
    out_tokens = int(usage.get("output_tokens", 0) or usage.get("completion_tokens", 0) or 0)
    if in_tokens or out_tokens:
        return in_tokens, out_tokens

    meta = getattr(response, "response_metadata", None) or {}
    token_usage = meta.get("token_usage", {}) if isinstance(meta, dict) else {}
    in_tokens = int(token_usage.get("input_tokens", 0) or token_usage.get("prompt_tokens", 0) or 0)
    out_tokens = int(token_usage.get("output_tokens", 0) or token_usage.get("completion_tokens", 0) or 0)
    return in_tokens, out_tokens


def _get_model_name(model: Any) -> str:
    return str(getattr(model, "model_name", None) or getattr(model, "model", "unknown"))


async def intent_gate_node(state: AgentState) -> dict:
    from .intent_router import IntentRouter

    chat_history = list(state.get("messages", []))[-6:]
    router = IntentRouter()
    decision = await router.classify(state["user_request"], chat_history=chat_history)

    result: dict = {
        "intent": decision.intent,
        "recommended_workflow": decision.recommended_workflow,
        "workflow_trace": ["intent_gate"],
        "messages": [
            AIMessage(
                content=(
                    f"Intent: {decision.intent} "
                    f"(confidence={decision.confidence:.2f}) | "
                    f"Workflow: {decision.recommended_workflow} | "
                    f"{decision.reasoning}"
                )
            )
        ],
    }
    if decision.recommended_workflow == "ask_clarification":
        result["final_answer"] = (
            "요청을 좀 더 명확히 알려주세요.\n"
            f"판단 이유: {decision.reasoning}"
        )
        result["loop_active"] = False
    return result


async def planner_node(state: AgentState) -> dict:
    from langchain_anthropic import ChatAnthropic
    from langchain_core.prompts import ChatPromptTemplate
    import json
    import re

    llm = ChatAnthropic(model="claude-opus-4-6")
    planner_prompt = """\
You are a strategic planner. Create a detailed execution plan for this request.

User request: {request}
Intent type: {intent}

Return ONLY valid JSON:
{{
  "tasks": [
    {{
      "id": "task-01",
      "title": "Clear title",
      "description": "What exactly to do",
      "agent": "researcher|coder|writer|analyst",
      "depends_on": [],
      "success_criteria": "How to verify done",
      "status": "pending"
    }}
  ],
  "acceptance_criteria": ["condition 1", "condition 2"]
}}

Keep tasks atomic (one clear action each). Maximum 7 tasks.
"""

    chain = ChatPromptTemplate.from_template(planner_prompt) | llm
    response = await chain.ainvoke({"request": state["user_request"], "intent": state["intent"]})
    json_match = re.search(r"\{.*\}", response.content, re.DOTALL)
    plan_data = json.loads(json_match.group()) if json_match else {"tasks": [], "acceptance_criteria": []}

    return {
        "plan": plan_data.get("tasks", []),
        "acceptance_criteria": plan_data.get("acceptance_criteria", []),
        "current_task_index": 0,
        "workflow_trace": ["planner"],
        "messages": [AIMessage(content=f"Plan created: {len(plan_data.get('tasks', []))} tasks")],
    }


async def executor_node(state: AgentState) -> dict:
    from .model_router import ModelRouter, TaskCategory

    plan = state.get("plan") or []
    current_index = state.get("current_task_index", 0)
    cost_guard = CostGuard(
        max_cost_usd=state.get("max_cost_usd", 1.0),
        max_tokens=state.get("max_tokens", 500_000),
        total_cost_usd=state.get("total_cost_usd", 0.0),
        total_tokens=state.get("total_tokens", 0),
    )

    # direct/research_only path
    if not plan:
        model = ModelRouter().get_model_for_intent(state["intent"])
        response = await model.ainvoke([HumanMessage(content=state["user_request"])])
        in_tokens, out_tokens = _extract_token_usage(response)
        cost_guard.record(_get_model_name(model), in_tokens, out_tokens)

        return {
            "final_answer": response.content,
            "loop_active": False,
            "total_cost_usd": cost_guard.total_cost_usd,
            "total_tokens": cost_guard.total_tokens,
            "workflow_trace": ["executor"],
            "messages": [AIMessage(content=response.content)],
        }

    if current_index >= len(plan):
        return {"loop_active": False}

    current_task = plan[current_index]
    agent_type = current_task.get("agent", "researcher")
    agent_to_category = {
        "researcher": TaskCategory.QUICK,
        "coder": TaskCategory.DEEP,
        "writer": TaskCategory.CREATIVE,
        "analyst": TaskCategory.ANALYSIS,
    }
    category = agent_to_category.get(agent_type, TaskCategory.QUICK)
    model = ModelRouter().get_model(category)

    task_prompt = (
        f"Task: {current_task['title']}\n"
        f"Description: {current_task['description']}\n"
        f"Success Criteria: {current_task['success_criteria']}\n"
        f"Original Request Context: {state['user_request']}"
    )
    response = await model.ainvoke([HumanMessage(content=task_prompt)])
    in_tokens, out_tokens = _extract_token_usage(response)
    cost_guard.record(_get_model_name(model), in_tokens, out_tokens)

    task_result: TaskResult = {
        "task_id": current_task["id"],
        "agent": agent_type,
        "result": response.content,
        "status": "success",
        "error": None,
    }
    return {
        "completed_tasks": [task_result],
        "current_task_index": current_index + 1,
        "consecutive_failures": 0,
        "loop_iteration": state.get("loop_iteration", 0) + 1,
        "total_cost_usd": cost_guard.total_cost_usd,
        "total_tokens": cost_guard.total_tokens,
        "loop_active": not cost_guard.is_over_limit(),
        "workflow_trace": [f"executor({agent_type})"],
        "messages": [AIMessage(content=f"Task '{current_task['title']}' completed.")],
    }


async def reviewer_node(state: AgentState) -> dict:
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(model="gpt-4o")
    completed = state.get("completed_tasks", [])
    results_summary = "\n".join(
        [f"- Task {r['task_id']} ({r['agent']}): {r['result'][:200]}..." for r in completed]
    )
    review_prompt = f"""
You are a technical reviewer. Assess if the work is complete.

Original Request: {state['user_request']}
Completed Tasks:
{results_summary}

Answer:
1. Is the original request fully addressed? (yes/no)
2. What's missing? (if anything)
3. Action needed: "approved" | "need_fix" | "replan"

Be concise. Maximum 3 sentences.
"""
    response = await model.ainvoke([HumanMessage(content=review_prompt)])
    return {
        "workflow_trace": ["reviewer"],
        "messages": [AIMessage(content=response.content)],
    }


async def finalizer_node(state: AgentState) -> dict:
    from langchain_anthropic import ChatAnthropic

    if state.get("final_answer"):
        return {"loop_active": False}

    model = ChatAnthropic(model="claude-sonnet-4-6")
    completed = state.get("completed_tasks", [])
    all_results = "\n\n".join([f"### {r['task_id']}\n{r['result']}" for r in completed])
    synthesize_prompt = f"""
Synthesize the following work into a clear, final answer.

Original request: {state['user_request']}

Work completed:
{all_results if all_results else "(No tasks completed - answer directly)"}

Provide a complete, well-structured final answer.
"""
    response = await model.ainvoke([HumanMessage(content=synthesize_prompt)])
    return {
        "final_answer": response.content,
        "loop_active": False,
        "workflow_trace": ["finalizer"],
        "messages": [AIMessage(content=response.content)],
    }


def build_orchestration_graph(checkpointer: Any | None = None):
    graph = StateGraph(AgentState)
    graph.add_node("intent_gate", intent_gate_node)
    graph.add_node("planner", planner_node)
    graph.add_node("executor", executor_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("loop_check", lambda s: s)
    graph.add_node("finalizer", finalizer_node)

    graph.set_entry_point("intent_gate")
    graph.add_conditional_edges(
        "intent_gate",
        route_by_intent,
        {"planner": "planner", "executor": "executor", "finalizer": "finalizer"},
    )
    graph.add_edge("planner", "executor")
    graph.add_conditional_edges(
        "executor",
        check_execution_result,
        {"reviewer": "reviewer", "executor": "executor", "finalizer": "finalizer"},
    )
    graph.add_conditional_edges(
        "reviewer",
        check_review_result,
        {"loop_check": "loop_check", "executor": "executor", "planner": "planner"},
    )
    graph.add_conditional_edges(
        "loop_check",
        should_continue_loop,
        {"executor": "executor", "finalizer": "finalizer"},
    )
    graph.add_edge("finalizer", END)

    if checkpointer is not None:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()
