from typing import TypedDict, Annotated, Sequence, Literal
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
import operator


# ─────────────────────────────────────────────
# 1. 워크플로우 상태 (oh-my-openagent의 세션 상태에 해당)
# ─────────────────────────────────────────────

class TaskItem(TypedDict):
    id: str
    title: str
    description: str
    agent: str
    depends_on: list[str]
    success_criteria: str
    status: str   # "pending" | "in_progress" | "done" | "failed"


class TaskResult(TypedDict):
    task_id: str
    agent: str
    result: str
    status: str   # "success" | "failed"
    error: str | None


class AgentState(TypedDict):
    """
    LangGraph 전체 워크플로우 상태.
    oh-my-openagent의 세션 상태 + Ralph Loop 상태를 통합.
    """
    # 기본 요청 정보
    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_request: str
    session_id: str

    # Intent Gate 결과
    intent: str                          # IntentType
    recommended_workflow: str            # "plan_execute" | "direct" | "research_only"

    # Planner 결과 (Prometheus 역할)
    plan: list[TaskItem] | None
    acceptance_criteria: list[str]

    # 실행 추적 (Atlas 역할)
    current_task_index: int
    completed_tasks: list[TaskResult]
    failed_tasks: list[TaskResult]

    # Ralph Loop 상태 (oh-my-openagent 핵심)
    loop_active: bool
    loop_iteration: int
    max_loop_iterations: int             # 기본값: 10

    # 에러 복구
    retry_count: int
    consecutive_failures: int

    # 최종 결과
    final_answer: str | None
    workflow_trace: list[str]            # 실행된 에이전트 이름 목록


# ─────────────────────────────────────────────
# 2. 라우팅 함수들 (LangGraph 조건부 엣지)
# ─────────────────────────────────────────────

def route_by_intent(state: AgentState) -> Literal["planner", "executor"]:
    """
    Intent Gate 결과에 따라 다음 노드를 결정한다.
    oh-my-openagent의 Phase 0 → Phase 1 분기에 해당.
    """
    workflow = state.get("recommended_workflow", "direct")

    if workflow == "plan_execute":
        return "planner"   # 계획 먼저
    else:
        return "executor"  # 바로 실행


def check_execution_result(state: AgentState) -> Literal["reviewer", "executor", "finalizer"]:
    """
    실행 결과를 보고 다음 단계를 결정한다.
    """
    consecutive = state.get("consecutive_failures", 0)
    retry = state.get("retry_count", 0)

    # 3회 연속 실패 → Oracle(reviewer) 상담 (oh-my-openagent 패턴)
    if consecutive >= 3:
        return "reviewer"

    # 재시도 한도 초과 → 강제 종료
    if retry >= 5:
        return "finalizer"

    completed = len(state.get("completed_tasks", []))
    plan = state.get("plan") or []
    total = len(plan)

    # 모든 태스크 완료 → 리뷰
    if completed >= total and total > 0:
        return "reviewer"

    # 아직 할 일 있음 → 계속 실행
    return "executor"


def check_review_result(state: AgentState) -> Literal["loop_check", "executor", "planner"]:
    """
    리뷰어 평가 후 다음 단계를 결정한다.
    """
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None

    if not last_message:
        return "loop_check"

    content = last_message.content if hasattr(last_message, "content") else ""

    # 리뷰어가 재계획을 요청한 경우
    if "replan" in content.lower() or "새로운 계획" in content:
        return "planner"

    # 리뷰어가 수정을 요청한 경우
    if "fix" in content.lower() or "need_fix" in content.lower():
        return "executor"

    # 기본: Loop 판단으로 이동
    return "loop_check"


def should_continue_loop(state: AgentState) -> Literal["executor", "finalizer"]:
    """
    Ralph Loop 판단 함수.
    oh-my-openagent의 loop-state-controller.ts를 Python으로 구현.

    "완료 조건을 달성했는가?" 를 판단하고:
    - 아직 할 일이 있으면 → 계속 실행
    - 모두 완료되었으면 → 종료
    """
    iteration = state.get("loop_iteration", 0)
    max_iter = state.get("max_loop_iterations", 10)

    # 최대 반복 횟수 초과
    if iteration >= max_iter:
        return "finalizer"

    # Loop가 비활성 상태
    if not state.get("loop_active", True):
        return "finalizer"

    plan = state.get("plan") or []
    completed = len(state.get("completed_tasks", []))
    total = len(plan)

    # 아직 완료 안 된 태스크가 있음
    if completed < total:
        return "executor"

    # 모든 태스크 완료 → 최종 답변 준비
    return "finalizer"


# ─────────────────────────────────────────────
# 3. 노드 함수들 (각 에이전트의 실행 로직)
# ─────────────────────────────────────────────

async def intent_gate_node(state: AgentState) -> dict:
    """
    Phase 0: Intent Gate
    의도를 분류하고 워크플로우를 결정한다.
    """
    from .intent_router import IntentRouter

    router = IntentRouter()
    decision = await router.classify(state["user_request"])

    return {
        "intent": decision.intent,
        "recommended_workflow": decision.recommended_workflow,
        "workflow_trace": state.get("workflow_trace", []) + ["intent_gate"],
        "messages": [
            AIMessage(content=f"Intent: {decision.intent} | Workflow: {decision.recommended_workflow} | {decision.reasoning}")
        ],
    }


async def planner_node(state: AgentState) -> dict:
    """
    Phase 1: Planner (Prometheus 역할)
    구체적인 실행 계획을 수립한다.
    """
    from langchain_anthropic import ChatAnthropic
    from langchain_core.prompts import ChatPromptTemplate
    import json

    llm = ChatAnthropic(model="claude-opus-4-6")

    PLANNER_PROMPT = """\
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

    prompt = ChatPromptTemplate.from_template(PLANNER_PROMPT)
    chain = prompt | llm

    response = await chain.ainvoke({
        "request": state["user_request"],
        "intent": state["intent"],
    })

    import re
    json_match = re.search(r"\{.*\}", response.content, re.DOTALL)
    plan_data = json.loads(json_match.group()) if json_match else {"tasks": [], "acceptance_criteria": []}

    return {
        "plan": plan_data.get("tasks", []),
        "acceptance_criteria": plan_data.get("acceptance_criteria", []),
        "current_task_index": 0,
        "workflow_trace": state.get("workflow_trace", []) + ["planner"],
        "messages": [AIMessage(content=f"Plan created: {len(plan_data.get('tasks', []))} tasks")],
    }


async def executor_node(state: AgentState) -> dict:
    """
    Phase 2: Executor (Atlas 역할)
    현재 태스크를 실행한다.
    """
    from langchain_anthropic import ChatAnthropic
    from .model_router import ModelRouter, TaskCategory

    plan = state.get("plan") or []
    current_index = state.get("current_task_index", 0)

    # 계획이 없는 경우 (direct 워크플로우)
    if not plan:
        model = ModelRouter().get_model_for_intent(state["intent"])
        response = await model.ainvoke([HumanMessage(content=state["user_request"])])
        return {
            "final_answer": response.content,
            "loop_active": False,
            "workflow_trace": state.get("workflow_trace", []) + ["executor"],
            "messages": [AIMessage(content=response.content)],
        }

    # 현재 태스크 실행
    if current_index >= len(plan):
        return {"loop_active": False}

    current_task = plan[current_index]
    agent_type = current_task.get("agent", "researcher")

    # 에이전트 타입에 따라 카테고리 결정
    agent_to_category = {
        "researcher": TaskCategory.QUICK,
        "coder":      TaskCategory.DEEP,
        "writer":     TaskCategory.CREATIVE,
        "analyst":    TaskCategory.ANALYSIS,
    }
    category = agent_to_category.get(agent_type, TaskCategory.QUICK)
    model = ModelRouter().get_model(category)

    task_prompt = f"""
Task: {current_task['title']}
Description: {current_task['description']}
Success Criteria: {current_task['success_criteria']}
Original Request Context: {state['user_request']}
"""
    response = await model.ainvoke([HumanMessage(content=task_prompt)])

    task_result: TaskResult = {
        "task_id": current_task["id"],
        "agent": agent_type,
        "result": response.content,
        "status": "success",
        "error": None,
    }

    return {
        "completed_tasks": state.get("completed_tasks", []) + [task_result],
        "current_task_index": current_index + 1,
        "consecutive_failures": 0,
        "loop_iteration": state.get("loop_iteration", 0) + 1,
        "workflow_trace": state.get("workflow_trace", []) + [f"executor({agent_type})"],
        "messages": [AIMessage(content=f"Task '{current_task['title']}' completed.")],
    }


async def reviewer_node(state: AgentState) -> dict:
    """
    Phase 3: Reviewer (Oracle 역할)
    결과물을 검토하고 완성도를 평가한다.
    """
    from langchain_openai import ChatOpenAI

    # Oracle은 GPT 모델 사용 (oh-my-openagent 패턴)
    model = ChatOpenAI(model="gpt-4o")

    completed = state.get("completed_tasks", [])
    results_summary = "\n".join([
        f"- Task {r['task_id']} ({r['agent']}): {r['result'][:200]}..."
        for r in completed
    ])

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
        "workflow_trace": state.get("workflow_trace", []) + ["reviewer"],
        "messages": [AIMessage(content=response.content)],
    }


async def finalizer_node(state: AgentState) -> dict:
    """
    최종 정리: 모든 결과를 종합해서 최종 답변 생성.
    """
    from langchain_anthropic import ChatAnthropic

    if state.get("final_answer"):
        return {"loop_active": False}

    model = ChatAnthropic(model="claude-sonnet-4-6")

    completed = state.get("completed_tasks", [])
    all_results = "\n\n".join([
        f"### {r['task_id']}\n{r['result']}"
        for r in completed
    ])

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
        "workflow_trace": state.get("workflow_trace", []) + ["finalizer"],
        "messages": [AIMessage(content=response.content)],
    }


# ─────────────────────────────────────────────
# 4. 워크플로우 그래프 조립
# ─────────────────────────────────────────────

def build_orchestration_graph():
    """
    oh-my-openagent의 4-Phase 오케스트레이션을 LangGraph로 구현.

    흐름:
    intent_gate → [planner|executor] → executor → reviewer → loop_check → [executor|finalizer]
    """
    graph = StateGraph(AgentState)

    # 노드 등록
    graph.add_node("intent_gate", intent_gate_node)
    graph.add_node("planner",     planner_node)
    graph.add_node("executor",    executor_node)
    graph.add_node("reviewer",    reviewer_node)
    graph.add_node("loop_check",  lambda s: s)  # 상태만 통과
    graph.add_node("finalizer",   finalizer_node)

    # 진입점
    graph.set_entry_point("intent_gate")

    # 조건부 엣지 (oh-my-openagent의 훅 기반 라우팅과 유사)
    graph.add_conditional_edges(
        "intent_gate",
        route_by_intent,
        {"planner": "planner", "executor": "executor"},
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

    # Ralph Loop 판단
    graph.add_conditional_edges(
        "loop_check",
        should_continue_loop,
        {"executor": "executor", "finalizer": "finalizer"},
    )

    graph.add_edge("finalizer", END)

    return graph.compile()
