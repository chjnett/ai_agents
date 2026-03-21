# My Agent System v2 — 고도화 아키텍처 가이드

> **작성일**: 2026-03-18  
> **업데이트**: 2026-03-19 (PHASE 1 구현 반영)  
> **버전**: 0.2 (고도화)  
> **배경**: 기술 검토 피드백 6가지를 반영한 업그레이드 설계

---

## 목차

1. [현재 구현 상태 (2026-03-19)](#1-현재-구현-상태-2026-03-19)
2. [v1 → v2 변경 요약](#2-v1--v2-변경-요약)
3. [Dynamic Tool Discovery](#3-dynamic-tool-discovery)
4. [Human-in-the-Loop (HITL)](#4-human-in-the-loop-hitl)
5. [Model Routing 고도화](#5-model-routing-고도화)
6. [병렬 실행 설계](#6-병렬-실행-설계)
7. [Observability — LangFuse 통합](#7-observability--langfuse-통합)
8. [Episodic Memory 설계](#8-episodic-memory-설계)
9. [업그레이드된 AgentState](#9-업그레이드된-agentstate)
10. [구현 우선순위 체크리스트](#10-구현-우선순위-체크리스트)

---

## 1. 현재 구현 상태 (2026-03-19)

### 완료된 PHASE 1 항목

- `src/core/cost_guard.py` 구현 완료
  - `PRICE_PER_1K`, `record()`, `is_over_limit()`, `summary()`
- `src/core/workflow_engine.py`에 `AgentState v2` 필드 반영
  - `total_cost_usd`, `total_tokens`, `max_cost_usd`, `max_tokens`
  - `user_id`, `task_complexity`, `parallel_groups`, `require_approval`
  - `past_episodes`, `user_preferences`
  - `completed_tasks`, `failed_tasks`, `workflow_trace`를 `Annotated[..., operator.add]` 적용
- 루프 안전장치 반영
  - `should_continue_loop()`와 `check_execution_result()`에 비용/토큰 하드캡 조건 추가
- 실행 중 비용 누적 반영
  - `executor_node()`에서 모델 호출 후 토큰 사용량 추출 및 `CostGuard.record()` 적용
- 체크포인터 연동 구조 반영
  - `build_orchestration_graph(checkpointer=None)` 지원
  - `main.py`에서 `thread_id=session_id`, `Command(resume=...)` 재개 흐름 반영
  - 로컬 환경에서 sqlite checkpointer 모듈 부재 시 non-persistent fallback 제공

### 현재 테스트 상태

- 전체 테스트: **27 passed / 0 failed**
- `tests/test_cost_guard.py` 추가 완료
- `tests/test_core.py`에 비용/토큰 루프 가드 및 초기 상태 팩토리 테스트 추가

---

## 2. v1 → v2 변경 요약

| 항목        | v1 (기존)            | v2 (개선)                            |
| ----------- | -------------------- | ------------------------------------ |
| 도구 할당   | 에이전트마다 고정    | 태스크별 동적 선택 (시맨틱 검색)     |
| 실행 흐름   | 승인 없이 자동 실행  | Planner 단계에서 Human Approval 대기 |
| 모델 선택   | 카테고리 → 고정 모델 | 카테고리 + 복잡도 → 2단계 선택       |
| 태스크 실행 | 순차 실행            | 의존성 없는 태스크 병렬 실행         |
| 비용 제어   | 반복 횟수만 제한     | 토큰 총량 + 비용 하드캡 추가         |
| 관찰 가능성 | 없음                 | LangFuse Trace 전면 통합             |
| 메모리      | 세션 내 유지만       | 에피소딕 메모리 (벡터 DB 장기 저장)  |

---

## 2. Dynamic Tool Discovery

### 문제 배경

에이전트마다 도구를 고정 할당하면:
- 수십 개 도구가 컨텍스트에 올라가 **윈도우 낭비**
- LLM이 불필요한 도구를 잘못 호출하는 **Tool-use Hallucination** 발생
- 새 도구 추가 시 에이전트 코드를 직접 수정해야 하는 **결합도 문제**

### 해결책: Semantic Tool Registry

```
태스크 설명
    │
    ▼
ToolRegistry.find_relevant(task_description, top_k=4)
    │  (임베딩 유사도 검색)
    ▼
관련 도구 3~4개만 추출
    │
    ▼
에이전트에 동적 주입 → LLM 호출
```

### 구현 설계

**파일**: `src/tools/registry.py`

```python
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.tools import BaseTool

class ToolRegistry:
    """
    도구를 벡터 DB에 등록하고, 태스크 설명과의
    시맨틱 유사도로 필요한 도구만 추출한다.
    """

    def __init__(self):
        self.embeddings = OpenAIEmbeddings()
        self._tools: dict[str, BaseTool] = {}
        self._vectorstore = Chroma(
            collection_name="tool_registry",
            embedding_function=self.embeddings,
        )

    def register(self, tool: BaseTool) -> None:
        """도구 등록 — 설명을 임베딩해서 벡터 DB에 저장"""
        self._tools[tool.name] = tool
        self._vectorstore.add_texts(
            texts=[f"{tool.name}: {tool.description}"],
            metadatas=[{"tool_name": tool.name}],
        )

    def find_relevant(self, task: str, top_k: int = 4) -> list[BaseTool]:
        """태스크와 가장 관련 높은 도구 top_k개 반환"""
        docs = self._vectorstore.similarity_search(task, k=top_k)
        return [
            self._tools[d.metadata["tool_name"]]
            for d in docs
            if d.metadata["tool_name"] in self._tools
        ]

    def get_all(self) -> list[BaseTool]:
        return list(self._tools.values())
```

### 에이전트 연동 방식

```python
# executor_node() 내부에서

registry = ToolRegistry()

# 현재 태스크 설명으로 관련 도구만 추출
relevant_tools = registry.find_relevant(
    task=current_task["description"],
    top_k=4,
)

# 에이전트에 동적으로 주입
agent = create_react_agent(model, tools=relevant_tools)
result = await agent.ainvoke({"input": task_prompt})
```

### 등록할 기본 도구 목록

| 도구 이름          | 설명 (임베딩 텍스트)                                     | 파일                      |
| ------------------ | -------------------------------------------------------- | ------------------------- |
| `web_search`       | Search the internet for current information and news     | `tools/web_search.py`     |
| `code_executor`    | Execute Python code and return output                    | `tools/code_executor.py`  |
| `file_read`        | Read file contents from the local filesystem             | `tools/file_manager.py`   |
| `file_write`       | Write or create files on the local filesystem            | `tools/file_manager.py`   |
| `knowledge_search` | Search internal knowledge base using semantic similarity | `tools/knowledge_base.py` |
| `vision_analyzer`  | Analyze screenshots, images, or diagrams                 | `tools/vision.py`         |

---

## 3. Human-in-the-Loop (HITL)

### 문제 배경

멀티-에이전트가 **실제 파일 수정·외부 API 호출** 같은 비가역적 작업을 수행할 때,  
사람의 확인 없이 자동 실행하면 치명적 실수가 발생할 수 있다.

oh-my-openagent의 `question: "allow"` 퍼미션 시스템을 LangGraph Breakpoint로 구현한다.

### LangGraph Interrupt 활용

```python
# workflow_engine.py

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt

async def planner_node(state: AgentState) -> dict:
    """계획 수립 후 — 사용자 승인 대기"""

    plan_data = await _generate_plan(state)

    # ★ Breakpoint: 계획을 보여주고 사용자 확인 대기
    if state.get("require_approval", True):
        user_feedback = interrupt({
            "type": "plan_approval",
            "plan": plan_data["tasks"],
            "acceptance_criteria": plan_data["acceptance_criteria"],
            "message": "실행할 계획입니다. 승인하시겠습니까? (approve/modify/cancel)",
        })

        if user_feedback == "cancel":
            return {"loop_active": False, "final_answer": "사용자가 취소했습니다."}

        if user_feedback.startswith("modify:"):
            # 수정 지시사항을 반영해서 재계획
            return await _replan_with_feedback(state, user_feedback[7:])

    return {
        "plan": plan_data["tasks"],
        "acceptance_criteria": plan_data["acceptance_criteria"],
        "current_task_index": 0,
    }


async def executor_node(state: AgentState) -> dict:
    """위험한 작업 전 추가 확인"""

    current_task = state["plan"][state["current_task_index"]]

    # 파일 쓰기, 외부 API 호출 태스크는 추가 확인
    RISKY_AGENTS = {"file_writer", "api_caller", "coder"}
    if current_task["agent"] in RISKY_AGENTS and state.get("require_approval"):
        confirmation = interrupt({
            "type": "task_approval",
            "task": current_task,
            "message": f"'{current_task['title']}' 를 실행합니다. 계속하시겠습니까?",
        })
        if confirmation == "cancel":
            return {"loop_active": False}

    # 태스크 실행
    ...
```

### Checkpointer 설정 (상태 영속성)

```python
# main.py

from langgraph.checkpoint.sqlite import SqliteSaver

# SQLite 체크포인터 (개발용)
checkpointer = SqliteSaver.from_conn_string("checkpoints.db")

# PostgreSQL 체크포인터 (운영용)
# from langgraph.checkpoint.postgres import PostgresSaver
# checkpointer = PostgresSaver.from_conn_string(os.getenv("DATABASE_URL"))

graph = build_orchestration_graph(checkpointer=checkpointer)

# 실행 — thread_id로 언제든 재개 가능
config = {"configurable": {"thread_id": session_id}}
result = await graph.ainvoke(initial_state, config=config)

# 중단된 세션 재개
# result = await graph.ainvoke(Command(resume="approve"), config=config)
```

### HITL 흐름 다이어그램

```
[Planner]
    │
    ▼
interrupt() ← 계획 표시
    │
    ├── "approve" → [Executor] 실행 시작
    ├── "modify: <지시>" → 재계획
    └── "cancel" → [Finalizer] 취소 메시지

[Executor - 위험 태스크]
    │
    ▼
interrupt() ← 태스크 상세 표시
    │
    ├── "approve" → 태스크 실행
    └── "cancel" → 루프 종료
```

### 승인 모드 설정

```python
# AgentState에 추가
require_approval: bool   # True = 사람 확인 필요, False = 완전 자동

# 환경별 기본값
DEV_MODE  → require_approval = True   (개발 중에는 항상 확인)
PROD_MODE → require_approval = False  (신뢰할 수 있는 사용자만)
```

---

## 4. Model Routing 고도화

### 기존 방식의 한계

```
TaskCategory.DEEP → claude-opus-4-6  (항상)
```

단순한 코멘트 수정도 Opus를 쓰면 **비용 낭비**.

### 2단계 복잡도 기반 선택

**1단계**: 카테고리 결정 (의도 기반)  
**2단계**: 복잡도 추정 → 경량/중간/중량 모델 선택

```python
# src/core/model_router.py

class ComplexityLevel(str, Enum):
    LOW    = "low"     # 단일 파일·단순 질문·짧은 수정
    MEDIUM = "medium"  # 다중 파일·중간 난이도
    HIGH   = "high"    # 아키텍처·전체 설계·복잡한 로직

# 카테고리 × 복잡도 → 모델
MODEL_MATRIX: dict[tuple[TaskCategory, ComplexityLevel], str] = {
    # DEEP (코딩)
    (TaskCategory.DEEP, ComplexityLevel.LOW):    "claude-haiku-4-5",
    (TaskCategory.DEEP, ComplexityLevel.MEDIUM): "claude-sonnet-4-6",
    (TaskCategory.DEEP, ComplexityLevel.HIGH):   "claude-opus-4-6",

    # ULTRABRAIN (추론)
    (TaskCategory.ULTRABRAIN, ComplexityLevel.LOW):    "gpt-4o-mini",
    (TaskCategory.ULTRABRAIN, ComplexityLevel.MEDIUM): "gpt-4o",
    (TaskCategory.ULTRABRAIN, ComplexityLevel.HIGH):   "gpt-4o",  # o3 가능

    # QUICK (정보 수집)
    (TaskCategory.QUICK, ComplexityLevel.LOW):    "claude-haiku-4-5",
    (TaskCategory.QUICK, ComplexityLevel.MEDIUM): "claude-haiku-4-5",
    (TaskCategory.QUICK, ComplexityLevel.HIGH):   "claude-sonnet-4-6",

    # CREATIVE (창작)
    (TaskCategory.CREATIVE, ComplexityLevel.LOW):    "claude-haiku-4-5",
    (TaskCategory.CREATIVE, ComplexityLevel.MEDIUM): "claude-sonnet-4-6",
    (TaskCategory.CREATIVE, ComplexityLevel.HIGH):   "claude-opus-4-6",

    # ANALYSIS (분석)
    (TaskCategory.ANALYSIS, ComplexityLevel.LOW):    "gpt-4o-mini",
    (TaskCategory.ANALYSIS, ComplexityLevel.MEDIUM): "gpt-4o",
    (TaskCategory.ANALYSIS, ComplexityLevel.HIGH):   "gpt-4o",
}


def estimate_complexity(task_description: str) -> ComplexityLevel:
    """
    태스크 설명에서 복잡도를 추정한다.
    LLM 호출 없이 규칙 기반으로 빠르게 판단.
    """
    desc = task_description.lower()

    HIGH_SIGNALS = [
        "architecture", "design", "refactor", "entire", "system",
        "아키텍처", "전체", "설계", "리팩토링",
    ]
    LOW_SIGNALS = [
        "fix typo", "rename", "comment", "one line", "simple",
        "오타", "이름 변경", "한 줄",
    ]

    if any(s in desc for s in HIGH_SIGNALS):
        return ComplexityLevel.HIGH
    if any(s in desc for s in LOW_SIGNALS):
        return ComplexityLevel.LOW
    return ComplexityLevel.MEDIUM


class ModelRouter:
    def get_model_v2(
        self,
        category: TaskCategory,
        task_description: str,
    ) -> BaseChatModel:
        complexity = estimate_complexity(task_description)
        model_name = MODEL_MATRIX.get(
            (category, complexity),
            "claude-sonnet-4-6",  # fallback
        )
        return self._create_model(model_name)
```

### 비용 하드캡 (Max Cost Guard)

```python
# src/core/cost_guard.py

class CostGuard:
    """
    세션당 토큰·비용 상한선을 강제한다.
    Ralph Loop가 무한히 돌면서 비용이 폭발하는 것을 막는다.
    """

    # 모델별 달러 단가 (2026-03 기준, 1K 토큰당)
    PRICE_PER_1K: dict[str, dict[str, float]] = {
        "claude-opus-4-6":   {"input": 0.015, "output": 0.075},
        "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
        "claude-haiku-4-5":  {"input": 0.00025, "output": 0.00125},
        "gpt-4o":            {"input": 0.005, "output": 0.015},
        "gpt-4o-mini":       {"input": 0.00015, "output": 0.0006},
    }

    def __init__(self, max_cost_usd: float = 1.0, max_tokens: int = 500_000):
        self.max_cost_usd = max_cost_usd
        self.max_tokens = max_tokens
        self.total_cost: float = 0.0
        self.total_tokens: int = 0

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        price = self.PRICE_PER_1K.get(model, {"input": 0.01, "output": 0.03})
        cost = (input_tokens * price["input"] + output_tokens * price["output"]) / 1000
        self.total_cost += cost
        self.total_tokens += input_tokens + output_tokens

    def is_over_limit(self) -> bool:
        return self.total_cost >= self.max_cost_usd or self.total_tokens >= self.max_tokens

    def summary(self) -> dict:
        return {
            "total_cost_usd": round(self.total_cost, 4),
            "total_tokens": self.total_tokens,
            "limit_exceeded": self.is_over_limit(),
        }
```

---

## 5. 병렬 실행 설계

### 문제 배경

현재 v1의 Executor는 태스크를 **순서대로 한 번에 하나씩** 실행한다.  
`depends_on`이 없는 독립 태스크들은 동시에 실행할 수 있어야 한다.

### LangGraph 병렬 브랜칭 설계

```
[Planner] → 5개 태스크 생성
               │
    ┌──────────┼──────────┐
    │          │          │
    ▼          ▼          ▼
task-01     task-02     task-03   (독립 태스크 → 동시 실행)
    │          │          │
    └──────────┴──────────┘
               │
            [merge_node]          (결과 취합)
               │
    ┌──────────┤
    │          │
    ▼          ▼
task-04    task-05               (task-01 결과 필요 → 순차)
    │          │
    └──────────┘
               │
           [Reviewer]
```

### 구현 설계

```python
# src/core/workflow_engine.py (병렬 실행 버전)

from langgraph.graph import Send

def parallel_dispatcher(state: AgentState) -> list[Send]:
    """
    의존성이 없는 태스크들을 동시에 전송한다.
    LangGraph의 Send API 활용.
    """
    plan = state.get("plan", [])
    completed_ids = {t["task_id"] for t in state.get("completed_tasks", [])}

    ready_tasks = [
        task for task in plan
        if task["status"] == "pending"
        and all(dep in completed_ids for dep in task.get("depends_on", []))
    ]

    if not ready_tasks:
        return []

    # 독립 태스크들을 병렬 전송
    return [
        Send("single_task_executor", {"task": task, **state})
        for task in ready_tasks
    ]


async def single_task_executor(state: dict) -> dict:
    """단일 태스크 실행 — 병렬 워커"""
    task = state["task"]
    # ... 태스크 실행 로직
    return {
        "completed_tasks": [TaskResult(
            task_id=task["id"],
            agent=task["agent"],
            result=result,
            status="success",
            error=None,
        )]
    }


async def merge_results(state: AgentState) -> dict:
    """병렬 실행 결과 취합"""
    # Annotated[list, operator.add]로 자동 누적됨
    # 여기서는 완료 상태 확인 후 다음 단계 결정
    return {"workflow_trace": state.get("workflow_trace", []) + ["merge"]}
```

### AgentState 병렬 지원 필드

```python
class AgentState(TypedDict):
    # 병렬 실행을 위해 list는 Annotated[list, operator.add] 사용
    completed_tasks: Annotated[list[TaskResult], operator.add]  # 병렬 결과 자동 누적
    failed_tasks: Annotated[list[TaskResult], operator.add]
    workflow_trace: Annotated[list[str], operator.add]
```

### 병렬 실행 가능 조건 판단

```python
def get_parallel_groups(plan: list[TaskItem]) -> list[list[TaskItem]]:
    """
    태스크를 의존성 기반으로 병렬 실행 그룹으로 분류.
    같은 그룹 내 태스크는 동시 실행 가능.
    """
    groups: list[list[TaskItem]] = []
    remaining = list(plan)
    completed_ids: set[str] = set()

    while remaining:
        # 현재 완료된 태스크에 의존하는 것들만 ready
        ready = [
            t for t in remaining
            if all(dep in completed_ids for dep in t.get("depends_on", []))
        ]
        if not ready:
            break  # 순환 의존성 방지
        groups.append(ready)
        completed_ids.update(t["id"] for t in ready)
        remaining = [t for t in remaining if t not in ready]

    return groups
```

---

## 6. Observability — LangFuse 통합

### 추적해야 할 메트릭

| 메트릭             | 설명                            | 활용                 |
| ------------------ | ------------------------------- | -------------------- |
| 노드별 실행시간    | 어느 Phase가 병목인가           | 최적화 우선순위 결정 |
| 모델별 토큰 소비   | 어느 모델이 비용을 쓰는가       | 비용 최적화          |
| 인텐트 분류 정확도 | 올바르게 분류되었는가           | 프롬프트 개선        |
| 루프 반복 횟수     | 몇 번 만에 완료되는가           | Ralph Loop 효율 측정 |
| 에러율             | 어느 에이전트가 자주 실패하는가 | 안정성 개선          |

### LangFuse 콜백 통합 설계

```python
# src/observability/langfuse_tracer.py

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langchain_core.callbacks import BaseCallbackHandler
import time

langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
)


def create_session_tracer(session_id: str) -> CallbackHandler:
    """세션별 LangFuse 트레이서 생성"""
    return CallbackHandler(
        trace_name=f"agent_session_{session_id}",
        session_id=session_id,
        tags=["my-agent-system", "v2"],
    )


class NodeTimingCallback(BaseCallbackHandler):
    """각 노드 실행 시간을 측정하는 콜백"""

    def __init__(self, node_name: str, session_id: str):
        self.node_name = node_name
        self.session_id = session_id
        self.start_time: float | None = None

    def on_llm_start(self, *args, **kwargs) -> None:
        self.start_time = time.time()

    def on_llm_end(self, response, **kwargs) -> None:
        if self.start_time:
            duration = time.time() - self.start_time
            # LangFuse에 커스텀 이벤트 로깅
            langfuse.create_event(
                name=f"node_completed_{self.node_name}",
                session_id=self.session_id,
                metadata={
                    "node": self.node_name,
                    "duration_seconds": round(duration, 2),
                    "model": response.llm_output.get("model_name", "unknown"),
                    "total_tokens": response.llm_output.get("token_usage", {}).get("total_tokens", 0),
                },
            )
```

### 노드별 적용 방법

```python
# executor_node() 내부

async def executor_node(state: AgentState) -> dict:
    session_id = state["session_id"]

    # 노드별 트레이서 생성
    tracer = create_session_tracer(session_id)
    timing_cb = NodeTimingCallback("executor", session_id)

    model = ModelRouter().get_model_v2(category, current_task["description"])
    model_with_callbacks = model.with_config(
        callbacks=[tracer, timing_cb]
    )

    result = await model_with_callbacks.ainvoke([HumanMessage(content=task_prompt)])
    ...
```

### LangFuse 대시보드에서 볼 수 있는 것

```
세션 타임라인:
  intent_gate   [0.3s] ─── Haiku
  planner       [2.1s] ─── Opus
  executor×3    [4.5s] ─── Sonnet (병렬)
  reviewer      [1.8s] ─── GPT-4o
  finalizer     [1.2s] ─── Sonnet
  ─────────────────────────
  total         9.9s  / $0.042
```

---

## 7. Episodic Memory 설계

### 개념

> "지난번에 이 사람은 TypeScript를 선호했어"  
> "JWT 구현할 때 이런 오류가 나서 이렇게 해결했었지"

에이전트가 과거 경험을 기억하고, 새 태스크에 활용한다.

### 3계층 메모리 구조

```
┌─────────────────────────────────────────────────────┐
│  Layer 1: Working Memory (현재 세션)                 │
│  AgentState.messages — 현재 대화 전체               │
├─────────────────────────────────────────────────────┤
│  Layer 2: Session Memory (Redis, 24시간)            │
│  AgentState 전체 — 세션 재개용                      │
├─────────────────────────────────────────────────────┤
│  Layer 3: Episodic Memory (ChromaDB, 영구)          │
│  성공 패턴 · 사용자 선호 · 해결된 오류 케이스        │
└─────────────────────────────────────────────────────┘
```

### 에피소드 저장 포맷

```python
# src/memory/episodic_memory.py

from pydantic import BaseModel
from datetime import datetime

class Episode(BaseModel):
    """하나의 성공적 작업 경험"""
    episode_id: str
    user_id: str | None
    created_at: datetime
    # 태스크 정보
    intent: str
    user_request_summary: str   # 요약 (개인정보 제거)
    # 학습된 내용
    successful_plan: list[dict] # 잘 작동한 계획
    key_insights: list[str]     # "JWT 기반 인증은 middleware 패턴으로"
    failed_approaches: list[str] # "직접 라우터에 검증 로직 넣으면 안됨"
    user_preferences: dict       # {"language": "TypeScript", "style": "functional"}
    # 메타
    workflow_duration_sec: float
    total_cost_usd: float


class EpisodicMemory:
    def __init__(self, vectorstore: Chroma):
        self.store = vectorstore

    async def save_episode(self, state: AgentState) -> None:
        """작업 완료 후 finalizer_node에서 호출"""
        episode = Episode(
            episode_id=state["session_id"],
            user_id=state.get("user_id"),
            created_at=datetime.now(),
            intent=state["intent"],
            user_request_summary=await _summarize_request(state["user_request"]),
            successful_plan=[t for t in (state.get("plan") or [])],
            key_insights=await _extract_insights(state),
            failed_approaches=[t["error"] for t in state.get("failed_tasks", []) if t.get("error")],
            user_preferences=state.get("user_preferences", {}),
            workflow_duration_sec=0.0,
            total_cost_usd=0.0,
        )
        # 벡터 DB에 저장
        self.store.add_texts(
            texts=[f"{episode.intent}: {episode.user_request_summary}\n{' '.join(episode.key_insights)}"],
            metadatas=[episode.model_dump()],
            ids=[episode.episode_id],
        )

    async def recall(self, task: str, top_k: int = 3) -> list[Episode]:
        """Planner가 계획 수립 전에 관련 경험 검색"""
        docs = self.store.similarity_search(task, k=top_k)
        return [Episode(**d.metadata) for d in docs]
```

### Planner에 메모리 주입

```python
async def planner_node(state: AgentState) -> dict:
    memory = EpisodicMemory(get_vectorstore())

    # 과거 유사 경험 검색
    past_episodes = await memory.recall(state["user_request"], top_k=3)
    memory_context = ""
    if past_episodes:
        insights = [ins for ep in past_episodes for ins in ep.key_insights]
        memory_context = f"""
Past experience (use as reference, not as strict rules):
{chr(10).join(f'- {i}' for i in insights[:5])}
"""

    # 계획 프롬프트에 과거 경험 주입
    plan_prompt = PLANNER_PROMPT.format(
        request=state["user_request"],
        intent=state["intent"],
        memory_context=memory_context,
    )
    ...
```

---

## 8. 업그레이드된 AgentState

v2에서 추가된 필드를 반영한 전체 `AgentState`.

```python
class AgentState(TypedDict):

    # ── 기본 요청 정보 ───────────────────────────────────────
    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_request: str
    session_id: str
    user_id: str | None                      # NEW: 사용자 식별 (메모리용)

    # ── Intent Gate 결과 ─────────────────────────────────────
    intent: str
    recommended_workflow: str
    task_complexity: str                     # NEW: "low" | "medium" | "high"

    # ── Planner 결과 ─────────────────────────────────────────
    plan: list[TaskItem] | None
    parallel_groups: list[list[str]] | None  # NEW: 병렬 실행 그룹
    acceptance_criteria: list[str]
    require_approval: bool                   # NEW: HITL 승인 필요 여부

    # ── 실행 추적 ─────────────────────────────────────────────
    current_task_index: int
    completed_tasks: Annotated[list[TaskResult], operator.add]  # 병렬 누적
    failed_tasks: Annotated[list[TaskResult], operator.add]

    # ── Ralph Loop 상태 ─────────────────────────────────────
    loop_active: bool
    loop_iteration: int
    max_loop_iterations: int

    # ── 비용 추적 (NEW) ─────────────────────────────────────
    total_cost_usd: float                    # NEW: 누적 비용
    total_tokens: int                        # NEW: 누적 토큰
    max_cost_usd: float                      # NEW: 비용 하드캡
    max_tokens: int                          # NEW: 토큰 하드캡

    # ── 에러 복구 ────────────────────────────────────────────
    retry_count: int
    consecutive_failures: int

    # ── 메모리 (NEW) ─────────────────────────────────────────
    past_episodes: list[dict] | None         # NEW: 관련 과거 경험
    user_preferences: dict                   # NEW: 사용자 선호 설정

    # ── 최종 결과 ────────────────────────────────────────────
    final_answer: str | None
    workflow_trace: Annotated[list[str], operator.add]
```

---

## 10. 구현 우선순위 체크리스트

### 필수 (Blocker — 이게 없으면 프로덕션 불가)

- [x] **비용 하드캡** `CostGuard` 구현 및 `AgentState`에 통합
- [x] **Ralph Loop 안전장치** `max_loop_iterations` + `max_cost_usd` 이중 가드
- [x] **LangGraph Checkpointer 연동 구조** (SQLite) — 세션 재개 흐름/스레드 ID 반영
- [ ] **HITL Breakpoint** — Planner 직후 사용자 승인 노드

### 권장 (Core Feature — 시스템 품질을 결정)

- [ ] **Dynamic Tool Registry** 시맨틱 검색 구현
- [ ] **2단계 Model Router** 카테고리 × 복잡도 매트릭스
- [ ] **LangFuse 통합** 모든 노드에 CallbackHandler 적용
- [ ] **병렬 태스크 실행** Send API + parallel_groups

### 심화 (고도화 — 경쟁력 강화)

- [ ] **Episodic Memory** ChromaDB + Episode 저장/검색
- [ ] **Vision Worker** 스크린샷·다이어그램 분석 에이전트
- [ ] **Pydantic AI 탐구** BaseAgent를 Pydantic AI 방식으로 재작성
- [ ] **FastAPI SSE** 실시간 스트리밍 응답

### 운영 (Ops — 장기 유지 보수)

- [ ] **에러 알림** 루프 실패 시 Slack/Discord 알림
- [ ] **비용 대시보드** LangFuse + 월별 예산 리포트
- [ ] **A/B 테스트** 모델 조합별 품질·비용 비교
- [ ] **자동 배포** GitHub Actions + Docker

---

*마지막 업데이트: 2026-03-19*
