# CODE_DEEP_DIVE.md — 현재 코드 완전 이해 & 개선 가이드

> **작성일**: 2026-03-18  
> **목적**: 현재 구현된 MVP 코드를 라인 단위로 분석하고, 각 부분이 **왜** 그렇게 작성됐는지 이해한 뒤, 어떻게 더 좋게 만들 수 있는지 개선 방향을 제시한다.

---

## 목차

1. [현재 구현 파일 목록](#1-현재-구현-파일-목록)
2. [intent_router.py 분석](#2-intent_routerpy-분석)
3. [model_router.py 분석](#3-model_routerpy-분석)
4. [workflow_engine.py 분석](#4-workflow_enginepy-분석)
5. [main.py 분석](#5-mainpy-분석)
6. [코드 전체 데이터 흐름](#6-코드-전체-데이터-흐름)
7. [현재 코드의 문제점 & 개선 방향](#7-현재-코드의-문제점--개선-방향)
8. [개선 순서 로드맵](#8-개선-순서-로드맵)

---

## 1. 현재 구현 파일 목록

```
src/core/
├── intent_router.py     104줄  → 의도 분류기
├── model_router.py       94줄  → 모델 선택기
└── workflow_engine.py   442줄  → 오케스트레이션 엔진 (핵심)

main.py                  152줄  → CLI 진입점
tests/test_core.py       ~130줄 → 단위 테스트
```

**총 구현 코드**: 약 **920줄**

---

## 2. `intent_router.py` 분석

### 전체 구조

```
IntentType (Enum)       ← 6가지 의도 타입 정의
RoutingDecision (Pydantic) ← 분류 결과 데이터 구조
INTENT_CLASSIFICATION_PROMPT ← LLM에 보내는 분류 프롬프트
IntentRouter (class)    ← 실제 분류 로직
```

### 라인별 핵심 분석

#### `IntentType` (9~15줄)

```python
class IntentType(str, Enum):
    RESEARCH    = "research"
    IMPLEMENT   = "implement"
    INVESTIGATE = "investigate"
    EVALUATE    = "evaluate"
    FIX         = "fix"
    GENERATE    = "generate"
```

**왜 `str, Enum` 조합인가?**  
- `str`을 상속하면 `IntentType.RESEARCH == "research"` 비교가 가능
- JSON 직렬화 시 `"research"` 문자열로 자동 변환
- LangGraph 상태(TypedDict)에 저장할 때 타입 오류 없음

**왜 6가지인가?**  
oh-my-openagent의 5가지 Phase(탐색·계획·구현·검토·완료)를 사용자 관점으로 재분류.  
`INVESTIGATE`와 `EVALUATE`를 분리한 이유: 조사("이거 왜 안 되지?")와 평가("이 방법이 좋을까?")는 답변 스타일이 달라야 함.

---

#### `RoutingDecision` (18~23줄)

```python
class RoutingDecision(BaseModel):
    intent: IntentType
    confidence: float          # 0.0 ~ 1.0
    reasoning: str             # 분류 이유
    recommended_workflow: str  # plan_execute | direct | research_only
    suggested_agents: list[str]
```

**왜 Pydantic BaseModel인가?**  
- LLM이 반환한 JSON을 자동 검증 + 타입 변환
- `confidence`가 문자열로 오면 자동으로 float 변환 시도
- 필드 누락 시 `ValidationError`로 명확한 오류

**`confidence`를 쓰는 이유?**  
현재는 사용하지 않지만, 나중에 "확신도가 0.6 미만이면 사용자에게 재확인" 같은 로직에 활용 예정.

**`recommended_workflow` 3종류의 의미**:

| 값              | 의미        | 어떤 의도에 쓰이나              |
| --------------- | ----------- | ------------------------------- |
| `plan_execute`  | 계획 → 실행 | implement, fix                  |
| `direct`        | 바로 실행   | investigate, evaluate, generate |
| `research_only` | 조사만      | research                        |

---

#### `INTENT_CLASSIFICATION_PROMPT` (26~57줄)

```python
INTENT_CLASSIFICATION_PROMPT = """\
You are an intent classifier for a multi-agent AI system.
...
Return ONLY valid JSON, no explanation:
{{
  "intent": "<intent_type>",
  ...
}}

User request: {user_request}
"""
```

**왜 `{{`와 `}}`를 쓰는가?**  
`ChatPromptTemplate.from_template()`은 `{변수}`를 포맷 변수로 인식.  
리터럴 중괄호를 표현하려면 `{{`로 이스케이프해야 함.

**프롬프트 설계 포인트**:
- `Return ONLY valid JSON` → LLM의 불필요한 설명을 막음
- Intent Types에 예시 문장 포함 → 분류 정확도 향상
- Workflow Recommendations를 프롬프트에 포함 → LLM이 직접 워크플로우 추천

---

#### `IntentRouter` 클래스 (60~103줄)

```python
def __init__(self, model_name: str = "claude-haiku-4-5"):
    self.llm = ChatAnthropic(model=model_name)
    self.prompt = ChatPromptTemplate.from_template(INTENT_CLASSIFICATION_PROMPT)
    self.chain = self.prompt | self.llm   # ← LangChain Expression Language (LCEL)
```

**`self.chain = self.prompt | self.llm` 이 한 줄의 의미**:  
LangChain의 파이프(`|`) 연산자 = LCEL (LangChain Expression Language).  
`prompt.invoke(input) → llm.invoke(result)` 를 간결하게 표현.  
`chain.ainvoke({"user_request": "..."})` 호출 시 자동으로 체인 실행.

```python
async def classify(self, user_request: str) -> RoutingDecision:
    response = await self.chain.ainvoke({"user_request": user_request})
    raw = response.content.strip()

    # JSON 블록 추출 (```json ... ``` 형태로 올 수도 있음)
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
```

**왜 `re.search(r"\{.*\}", raw, re.DOTALL)`인가?**  
LLM이 아래처럼 마크다운 코드블록으로 감쌀 수도 있음:
```
Here is the JSON:
```json
{"intent": "research", ...}
```
```
`re.DOTALL` 플래그 = `.`이 줄바꿈도 매칭.  
첫 번째 `{`부터 마지막 `}`까지 통째로 추출.

**폴백 처리 (87~95줄)**:
```python
if not json_match:
    return RoutingDecision(
        intent=IntentType.RESEARCH,
        confidence=0.5,
        reasoning="Classification failed, defaulting to research",
        recommended_workflow="research_only",
        suggested_agents=["researcher"],
    )
```
JSON 파싱이 실패해도 예외를 던지지 않고 안전한 기본값 반환.  
`research_only`가 기본값인 이유: 가장 안전한 워크플로우 (읽기만, 쓰기 안 함).

### ⚠️ 현재 문제점

1. **`IntentRouter` 인스턴스가 매번 새로 생성됨** → `workflow_engine.py`의 `intent_gate_node()`에서 `IntentRouter()` 호출 시마다 새 객체
2. **JSON 파싱 에러가 조용히 묻힘** → `json.loads()` 실패 시 예외가 아닌 빈 dict로 처리됨
3. **프롬프트가 파일 안 상수** → 수정할 때마다 코드 건드려야 함

---

## 3. `model_router.py` 분석

### 전체 구조

```
TaskCategory (Enum)          ← 6가지 태스크 카테고리
MODEL_CATEGORY_MAPPING       ← 카테고리 → 모델명 dict
FALLBACK_CHAIN               ← 실패 시 순서대로 시도할 모델 목록
ModelRouter (class)          ← 실제 모델 선택 로직
```

### 라인별 핵심 분석

#### `TaskCategory` (8~19줄)

```python
class TaskCategory(str, Enum):
    QUICK      = "quick"       # 단순 빠른 작업
    DEEP       = "deep"        # 심층 자율 작업
    VISUAL     = "visual"      # 시각/프론트엔드
    ULTRABRAIN = "ultrabrain"  # 최고 난이도 추론
    CREATIVE   = "creative"    # 창작, 글쓰기
    ANALYSIS   = "analysis"    # 데이터 분석
```

**왜 의도(Intent)와 카테고리(Category)를 분리했나?**  
- `Intent` = 사용자가 **무엇을 원하는가** (요청 관점)
- `Category` = 이 작업에 **어떤 능력의 모델이 필요한가** (모델 선택 관점)

예: `fix` 의도 → `DEEP` 카테고리 (코드를 깊이 이해해야 하니까)  
예: `research` 의도 → `QUICK` 카테고리 (정보 수집은 빠르면 충분)

---

#### `MODEL_CATEGORY_MAPPING` (24~31줄)

```python
MODEL_CATEGORY_MAPPING: dict[TaskCategory, str] = {
    TaskCategory.QUICK:      "claude-haiku-4-5",   # 빠르고 저렴
    TaskCategory.DEEP:       "claude-opus-4-6",    # 심층 작업
    TaskCategory.VISUAL:     "gemini-2.5-pro",     # 비전 강점
    TaskCategory.ULTRABRAIN: "gpt-4o",             # 추론 강점
    TaskCategory.CREATIVE:   "claude-sonnet-4-6",  # 창작 강점
    TaskCategory.ANALYSIS:   "gpt-4o",             # 분석 강점
}
```

**모델 선택 근거**:

| 카테고리   | 선택 모델 | 이유                                    |
| ---------- | --------- | --------------------------------------- |
| QUICK      | Haiku     | 분류·요약처럼 단순한 건 빠르고 저렴하게 |
| DEEP       | Opus      | 복잡한 코드 이해·아키텍처는 최고 모델   |
| VISUAL     | Gemini    | 이미지 이해·UI 작업은 Gemini가 강점     |
| ULTRABRAIN | GPT-4o    | 수학·논리·추론은 GPT가 강점             |
| CREATIVE   | Sonnet    | 글쓰기는 Claude Sonnet이 균형적         |
| ANALYSIS   | GPT-4o    | 데이터 패턴 인식은 GPT가 강점           |

**`FALLBACK_CHAIN` (34~39줄)** — 현재 미사용:
```python
FALLBACK_CHAIN: list[str] = [
    "claude-opus-4-6",
    "gpt-4o",
    "gemini-2.5-pro",
    "claude-sonnet-4-6",
]
```
API 호출 실패 시 순서대로 다음 모델 시도하는 용도. 아직 구현 안 됨.

---

#### `ModelRouter._create_model()` (65~77줄)

```python
def _create_model(self, model_name: str) -> BaseChatModel:
    name_lower = model_name.lower()

    if "claude" in name_lower:
        return ChatAnthropic(model=model_name)
    elif "gpt" in name_lower or "o1" in name_lower or "o3" in name_lower:
        return ChatOpenAI(model=model_name)
    elif "gemini" in name_lower:
        return ChatGoogleGenerativeAI(model=model_name)
    else:
        return ChatAnthropic(model="claude-haiku-4-5")  # 기본값
```

**문자열 매칭으로 프로바이더 감지하는 이유**:  
모델명 규칙이 일정하기 때문에 별도 매핑 테이블 없이 간단하게 처리 가능.  
`"o1"`, `"o3"` 조건 추가 = 향후 OpenAI o-시리즈 모델 대응.

---

#### `get_model_for_intent()` (79~93줄)

```python
def get_model_for_intent(self, intent: str) -> BaseChatModel:
    intent_to_category = {
        "research":    TaskCategory.QUICK,
        "implement":   TaskCategory.DEEP,
        "investigate": TaskCategory.ANALYSIS,
        "evaluate":    TaskCategory.ULTRABRAIN,
        "fix":         TaskCategory.DEEP,
        "generate":    TaskCategory.CREATIVE,
    }
    category = intent_to_category.get(intent, TaskCategory.QUICK)
    return self.get_model(category)
```

**`executor_node()`의 `direct` 워크플로우에서 사용**:  
계획 없이 바로 실행할 때 의도 → 카테고리 → 모델을 한 번에 결정.

### ⚠️ 현재 문제점

1. **모델 고정** → 복잡도에 상관없이 항상 같은 모델 (비용 최적화 불가)
2. **`FALLBACK_CHAIN` 미사용** → API 실패 시 그냥 예외 발생
3. **`ModelRouter()` 매번 새로 생성** → 상태 없는 객체지만 오버헤드

---

## 4. `workflow_engine.py` 분석

### 전체 구조 (442줄)

```
Section 1 (7~63줄):   데이터 구조 (TaskItem, TaskResult, AgentState)
Section 2 (66~163줄): 라우팅 함수 4개 (조건부 엣지 결정자)
Section 3 (166~384줄): 노드 함수 5개 (각 Phase의 실행 로직)
Section 4 (387~441줄): 그래프 조립 (build_orchestration_graph)
```

---

### Section 1: 데이터 구조

#### `TaskItem` (11~18줄)

```python
class TaskItem(TypedDict):
    id: str                # "task-01", "task-02"
    title: str             # 한 줄 제목
    description: str       # 상세 설명
    agent: str             # "researcher"|"coder"|"writer"|"analyst"
    depends_on: list[str]  # 선행 태스크 ID 목록
    success_criteria: str  # 완료 판단 기준
    status: str            # 상태
```

**왜 TypedDict인가?** (Pydantic이 아닌 이유)  
LangGraph `AgentState`가 `TypedDict`이므로 그 안의 항목도 `TypedDict`으로 통일.  
런타임 검증이 필요 없고, 타입 힌트만 있으면 충분.

**`depends_on`의 의미**:  
나중에 병렬 실행 시 이 목록이 비어있으면 즉시 시작 가능.  
`["task-01", "task-02"]`이면 두 태스크 완료 후에만 시작.

---

#### `AgentState` (29~63줄)

```python
class AgentState(TypedDict):
    # 기본 정보
    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_request: str
    session_id: str

    # Intent Gate 결과
    intent: str
    recommended_workflow: str

    # Planner 결과
    plan: list[TaskItem] | None
    acceptance_criteria: list[str]

    # 실행 추적
    current_task_index: int
    completed_tasks: list[TaskResult]
    failed_tasks: list[TaskResult]

    # Ralph Loop 상태
    loop_active: bool
    loop_iteration: int
    max_loop_iterations: int

    # 에러 복구
    retry_count: int
    consecutive_failures: int

    # 최종 결과
    final_answer: str | None
    workflow_trace: list[str]
```

**`Annotated[Sequence[BaseMessage], operator.add]` 의 의미**:  
LangGraph에서 상태 업데이트 시 기본 동작은 **덮어쓰기**.  
`operator.add`를 지정하면 **누적(append)** 동작으로 바뀜.  
즉, 각 노드가 `{"messages": [new_msg]}` 를 반환하면 기존 목록에 추가됨.

**현재 `completed_tasks`는 `Annotated` 없음 → 문제**:
```python
completed_tasks: list[TaskResult]  # 현재: 덮어쓰기
```
병렬 실행 지원 시 반드시:
```python
completed_tasks: Annotated[list[TaskResult], operator.add]  # 개선: 누적
```

---

### Section 2: 라우팅 함수

#### `route_by_intent()` (70~80줄)

```python
def route_by_intent(state: AgentState) -> Literal["planner", "executor"]:
    workflow = state.get("recommended_workflow", "direct")
    if workflow == "plan_execute":
        return "planner"
    else:
        return "executor"
```

**LangGraph `add_conditional_edges`가 이 함수를 호출하는 방식**:  
`graph.add_conditional_edges("intent_gate", route_by_intent, {...})`  
→ `intent_gate` 노드 실행 후 `route_by_intent(현재_state)` 호출  
→ 반환값에 해당하는 노드로 이동  

**`.get("recommended_workflow", "direct")` 왜 `.get`인가?**  
TypedDict를 `dict.get()`으로 쓰는 이유: 실제 런타임에서 필드가 없을 수 있음.  
(LangGraph가 부분 업데이트만 처리할 때 일부 필드가 nuLL일 수 있음)

---

#### `check_execution_result()` (83~107줄)

```python
def check_execution_result(state) -> Literal["reviewer", "executor", "finalizer"]:
    consecutive = state.get("consecutive_failures", 0)
    retry = state.get("retry_count", 0)

    if consecutive >= 3:      # 3회 연속 실패 → Oracle 상담
        return "reviewer"
    if retry >= 5:            # 5회 총 재시도 → 강제 종료
        return "finalizer"

    completed = len(state.get("completed_tasks", []))
    total = len(state.get("plan") or [])

    if completed >= total and total > 0:   # 모두 완료 → 리뷰
        return "reviewer"

    return "executor"   # 아직 남음 → 계속
```

**`3회 연속 실패 → Reviewer(Oracle)` 패턴의 의미**:  
oh-my-openagent의 Phase 2C (Failure Recovery)를 구현.  
직접 고치려다 3번 실패하면, 더 높은 수준의 에이전트에게 방향을 물어봄.   
이것이 단순 재시도와 다른 점: **전략을 바꾼다**.

---

#### `check_review_result()` (110~131줄)

```python
def check_review_result(state) -> Literal["loop_check", "executor", "planner"]:
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None

    content = last_message.content if hasattr(last_message, "content") else ""

    if "replan" in content.lower() or "새로운 계획" in content:
        return "planner"
    if "fix" in content.lower() or "need_fix" in content.lower():
        return "executor"
    return "loop_check"
```

**⚠️ 현재 가장 취약한 코드**:  
리뷰어 응답에서 `"fix"` 키워드를 단순 문자열 매칭으로 판단.  
리뷰어가 `"This fix is approved"` 라고 해도 `"fix"` 포함이라 `executor`로 분기될 수 있음.  
**개선 필요**: 리뷰어 응답을 구조화된 JSON으로 강제.

---

#### `should_continue_loop()` (134~163줄)

```python
def should_continue_loop(state) -> Literal["executor", "finalizer"]:
    iteration = state.get("loop_iteration", 0)
    max_iter = state.get("max_loop_iterations", 10)

    if iteration >= max_iter:       # 한도 초과
        return "finalizer"
    if not state.get("loop_active", True):  # 명시적 종료
        return "finalizer"

    plan = state.get("plan") or []
    completed = len(state.get("completed_tasks", []))

    if completed < len(plan):   # 미완료 태스크 있음
        return "executor"
    return "finalizer"          # 모두 완료
```

**이것이 Ralph Loop의 핵심**:  
"아직 할 일이 있으면 계속, 없으면 멈춰라"  
`max_iter` 체크가 첫 번째 조건인 이유: **안전장치 우선**.  
아무리 할 일이 많아도 10번 이상은 돌지 않는다.

---

### Section 3: 노드 함수

#### `intent_gate_node()` (170~187줄)

```python
async def intent_gate_node(state: AgentState) -> dict:
    from .intent_router import IntentRouter   # ← 지연 import

    router = IntentRouter()   # ← 매번 새로 생성
    decision = await router.classify(state["user_request"])

    return {
        "intent": decision.intent,
        "recommended_workflow": decision.recommended_workflow,
        "workflow_trace": state.get("workflow_trace", []) + ["intent_gate"],
        "messages": [AIMessage(content=f"Intent: {decision.intent} | ...")],
    }
```

**지연 import (`from .intent_router import ...`) 이유**:  
모듈 최상위에 import하면 파일 로드 시 순환 import 위험 가능.  
함수 안에서 import하면 실제 실행 시점에 임포트 → 안전.

**반환 dict의 의미**:  
LangGraph는 노드 반환값을 현재 `AgentState`에 **병합(merge)** 함.  
반환하지 않은 필드는 이전 값 유지.  
`workflow_trace`는 기존 리스트 + `["intent_gate"]` = 누적  
(하지만 `Annotated[list, operator.add]` 없이 수동 누적 → 비효율)

---

#### `planner_node()` (190~244줄)

```python
async def planner_node(state: AgentState) -> dict:
    from langchain_anthropic import ChatAnthropic
    from langchain_core.prompts import ChatPromptTemplate
    import json

    llm = ChatAnthropic(model="claude-opus-4-6")

    PLANNER_PROMPT = """\
You are a strategic planner. ...
Return ONLY valid JSON:
...
"""
    prompt = ChatPromptTemplate.from_template(PLANNER_PROMPT)
    chain = prompt | llm
    response = await chain.ainvoke({...})

    import re
    json_match = re.search(r"\{.*\}", response.content, re.DOTALL)
    plan_data = json.loads(json_match.group()) if json_match else {"tasks": [], ...}
    ...
```

**⚠️ 가장 큰 문제**: 프롬프트가 함수 내부 지역변수  
매번 함수 호출 시 동일한 프롬프트 재생성 = 성능 낭비.  
모듈 상수로 분리해야 함.

**`json_match` 패턴 재사용**:  
`intent_router.py`의 JSON 추출 로직과 동일.  
중복 코드 → 공통 유틸 함수 `extract_json(text) -> dict` 로 추출 필요.

---

#### `executor_node()` (247~309줄)

```python
async def executor_node(state: AgentState) -> dict:
    plan = state.get("plan") or []
    current_index = state.get("current_task_index", 0)

    # Case A: 계획 없음 (direct 워크플로우)
    if not plan:
        model = ModelRouter().get_model_for_intent(state["intent"])
        response = await model.ainvoke([HumanMessage(content=state["user_request"])])
        return {"final_answer": response.content, "loop_active": False, ...}

    # Case B: 계획 있음
    current_task = plan[current_index]
    agent_type = current_task.get("agent", "researcher")

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
...
"""
    response = await model.ainvoke([HumanMessage(content=task_prompt)])
    ...
```

**이 파일에서 가장 많은 책임을 지는 노드**:  
- 계획 O/X 분기 처리
- 에이전트 타입 → 카테고리 매핑
- 태스크별 실행
- 결과 저장

**리팩터링이 가장 시급한 곳** → Phase 2에서 Worker 에이전트 클래스로 분리.

---

#### `reviewer_node()` (312~347줄)

```python
async def reviewer_node(state: AgentState) -> dict:
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(model="gpt-4o")  # Claude 결과를 GPT로 교차 검증

    results_summary = "\n".join([
        f"- Task {r['task_id']} ({r['agent']}): {r['result'][:200]}..."
        for r in completed
    ])

    review_prompt = f"""
...
3. Action needed: "approved" | "need_fix" | "replan"
Be concise. Maximum 3 sentences.
"""
    response = await model.ainvoke([HumanMessage(content=review_prompt)])
    return {..., "messages": [AIMessage(content=response.content)]}
```

**결과를 200자로 자르는 이유 (`r['result'][:200]`)**:  
컨텍스트 윈도우 절약. 리뷰어에게 전체 결과가 아닌 요약만.  
하지만 이 방식은 너무 단순 — 중요한 내용이 200자 이후에 있을 수 있음.  
**개선**: 결과를 먼저 요약해서 전달.

**리뷰어 응답이 자유 텍스트 → 문제**:  
"3. Action needed: approved" 를 `check_review_result()`가 파싱해야 함.  
현재는 단순 문자열 매칭 → 오류 가능성 높음.  
**개선**: 리뷰어도 JSON으로 응답하게 프롬프트 수정.

---

#### `finalizer_node()` (350~384줄)

```python
async def finalizer_node(state: AgentState) -> dict:
    if state.get("final_answer"):
        return {"loop_active": False}  # 이미 있으면 그대로

    model = ChatAnthropic(model="claude-sonnet-4-6")

    all_results = "\n\n".join([
        f"### {r['task_id']}\n{r['result']}"
        for r in completed
    ])

    synthesize_prompt = f"""
Synthesize the following work into a clear, final answer.
...
"""
    response = await model.ainvoke(...)
    return {"final_answer": response.content, "loop_active": False, ...}
```

**이미 `final_answer`가 있으면 바로 반환하는 이유**:  
`direct` 워크플로우에서 `executor_node()`가 이미 `final_answer`를 설정했을 수 있음.  
재실행 방지 = 비용 절약.

---

### Section 4: 그래프 조립

#### `build_orchestration_graph()` (391~441줄)

```python
def build_orchestration_graph():
    graph = StateGraph(AgentState)

    # 6개 노드 등록
    graph.add_node("intent_gate", intent_gate_node)
    graph.add_node("planner",     planner_node)
    graph.add_node("executor",    executor_node)
    graph.add_node("reviewer",    reviewer_node)
    graph.add_node("loop_check",  lambda s: s)   # 통과 노드
    graph.add_node("finalizer",   finalizer_node)

    graph.set_entry_point("intent_gate")

    # 조건부 엣지 4개
    graph.add_conditional_edges("intent_gate", route_by_intent, {...})
    graph.add_edge("planner", "executor")  # planner → executor 항상
    graph.add_conditional_edges("executor", check_execution_result, {...})
    graph.add_conditional_edges("reviewer", check_review_result, {...})
    graph.add_conditional_edges("loop_check", should_continue_loop, {...})

    graph.add_edge("finalizer", END)

    return graph.compile()
```

**`lambda s: s` (loop_check 노드)**:  
상태를 변경하지 않고 그냥 통과시키는 노드.  
존재하는 이유: LangGraph에서 `add_conditional_edges`는 노드에서만 출발 가능.  
`reviewer → should_continue_loop → executor/finalizer` 를 직접 연결할 수 없어서 빈 중간 노드 사용.

**`graph.compile()`**:  
외부에서 `checkpointer`를 받을 수 있어야 HITL 구현 가능.  
현재: `graph.compile()` → 파라미터 없음  
개선: `graph.compile(checkpointer=checkpointer)`

---

## 5. `main.py` 분석

### 초기 상태 딕셔너리 (57~74줄)

```python
initial_state = {
    "messages": [],
    "user_request": user_input,
    "session_id": session_id,
    "intent": "",
    "recommended_workflow": "direct",
    "plan": None,
    "acceptance_criteria": [],
    "current_task_index": 0,
    "completed_tasks": [],
    "failed_tasks": [],
    "loop_active": True,
    "loop_iteration": 0,
    "max_loop_iterations": 10,
    "retry_count": 0,
    "consecutive_failures": 0,
    "final_answer": None,
    "workflow_trace": [],
}
```

**모든 필드를 직접 초기화해야 하는 이유**:  
`TypedDict`는 기본값 설정 불가.  
Pydantic Model이었다면 `default_factory`로 해결 가능.  
**개선**: `make_initial_state(user_request, session_id)` 팩토리 함수 추출.

---

## 6. 코드 전체 데이터 흐름

```
main.py
  main() → run_interactive() / run_demo()
    │
    ▼
initial_state 딕셔너리 생성
    │
    ▼
graph.ainvoke(initial_state)
    │
    ▼  ─────────── LangGraph 내부 실행 ───────────
    │
[intent_gate_node]
  IntentRouter().classify()
    → PROMPT | Claude Haiku → JSON 파싱
    → state["intent"] = "research"
    → state["recommended_workflow"] = "research_only"
    │
    ▼ route_by_intent()
    │ "plan_execute" → [planner]
    │ else           → [executor]
    │
[planner_node] ← plan_execute만
  Claude Opus → JSON 파싱
    → state["plan"] = [TaskItem, ...]
    → state["current_task_index"] = 0
    │
    ▼ (항상 executor로)
    │
[executor_node] ← 반복 실행
  state["plan"][current_index] 꺼냄
  agent_type → category → ModelRouter → LLM 호출
    → state["completed_tasks"] += [TaskResult]
    → state["current_task_index"] += 1
    │
    ▼ check_execution_result()
    │ consecutive_failures >= 3  → [reviewer]
    │ completed >= total         → [reviewer]
    │ else                       → [executor] 반복
    │
[reviewer_node]
  GPT-4o → "approved|need_fix|replan"
    │
    ▼ check_review_result()
    │ "replan"    → [planner]
    │ "fix"       → [executor]
    │ else        → [loop_check]
    │
[loop_check] (통과 노드)
    │
    ▼ should_continue_loop()
    │ completed < total → [executor]
    │ else              → [finalizer]
    │
[finalizer_node]
  Claude Sonnet → 결과 합성
    → state["final_answer"] = "..."
    │
    ▼ END
    │
graph.ainvoke() 반환
    │
final_state["final_answer"] 출력
```

---

## 7. 현재 코드의 문제점 & 개선 방향

### 🔴 Critical (지금 바로 고쳐야 함)

#### 문제 1: `check_review_result()` 키워드 매칭 취약

```python
# 현재 (취약)
if "fix" in content.lower():
    return "executor"

# 개선: 리뷰어 응답을 JSON으로 강제
```

**개선 방법**: `reviewer_node()`의 프롬프트 수정

```python
REVIEWER_PROMPT = """
...
Return ONLY JSON:
{
  "is_complete": true/false,
  "missing": ["item 1", "item 2"],
  "action": "approved" | "need_fix" | "replan",
  "feedback": "one sentence"
}
"""
```

`check_review_result()` 도 JSON 파싱으로 변경:
```python
def check_review_result(state) -> Literal["loop_check", "executor", "planner"]:
    last = state.get("messages", [])[-1]
    data = extract_json(last.content)
    action = data.get("action", "approved")
    if action == "replan":   return "planner"
    if action == "need_fix": return "executor"
    return "loop_check"
```

---

#### 문제 2: 프롬프트 + import가 함수 내부에 있음

```python
# 현재 (매 호출마다 재생성)
async def planner_node(state):
    from langchain_anthropic import ChatAnthropic
    import json
    import re
    llm = ChatAnthropic(model="claude-opus-4-6")
    PLANNER_PROMPT = "..."   # 매번 재정의
    ...
```

**개선**: 모듈 최상위로 이동

```python
# 상단에 한 번만
from langchain_anthropic import ChatAnthropic
import json, re

_PLANNER_LLM = ChatAnthropic(model="claude-opus-4-6")
_PLANNER_PROMPT = ChatPromptTemplate.from_template("""...""")
_PLANNER_CHAIN = _PLANNER_PROMPT | _PLANNER_LLM

async def planner_node(state):
    response = await _PLANNER_CHAIN.ainvoke({...})
    ...
```

---

#### 문제 3: JSON 추출 로직 중복 (intent_router + workflow_engine)

```python
# 두 곳에 동일한 코드
json_match = re.search(r"\{.*\}", raw, re.DOTALL)
plan_data = json.loads(json_match.group()) if json_match else {}
```

**개선**: 공통 유틸 함수

```python
# src/core/utils.py
def extract_json(text: str) -> dict:
    """LLM 응답에서 JSON 블록을 추출하고 파싱한다."""
    match = re.search(r"\{.*\}", text.strip(), re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {}
```

---

### 🟡 Important (다음 단계에서 개선)

#### 문제 4: `initial_state` 중복 생성

`main.py`에 `run_interactive()`와 `run_demo()`가 거의 같은 초기 상태를 중복 정의.  

**개선**: 팩토리 함수

```python
# src/core/workflow_engine.py에 추가
def make_initial_state(
    user_request: str,
    session_id: str,
    max_loop_iterations: int = 10,
) -> AgentState:
    return {
        "messages": [],
        "user_request": user_request,
        "session_id": session_id,
        "intent": "",
        "recommended_workflow": "direct",
        "plan": None,
        "acceptance_criteria": [],
        "current_task_index": 0,
        "completed_tasks": [],
        "failed_tasks": [],
        "loop_active": True,
        "loop_iteration": 0,
        "max_loop_iterations": max_loop_iterations,
        "retry_count": 0,
        "consecutive_failures": 0,
        "final_answer": None,
        "workflow_trace": [],
    }
```

---

#### 문제 5: `completed_tasks`가 병렬 누적 미지원

```python
# 현재 (덮어쓰기)
completed_tasks: list[TaskResult]

# 개선 (자동 누적)
completed_tasks: Annotated[list[TaskResult], operator.add]
```

---

#### 문제 6: `ModelRouter`가 매번 새로 생성됨

```python
# executor_node()에서 매번
model = ModelRouter().get_model(category)  # 새 객체 생성

# 개선: 모듈 레벨 싱글톤
_MODEL_ROUTER = ModelRouter()

async def executor_node(state):
    model = _MODEL_ROUTER.get_model(category)
```

---

### 🟢 Enhancement (여유 있을 때)

#### 문제 7: 에러 처리 부재

현재 LLM 호출 시 네트워크 에러, API 제한 등이 발생하면 그냥 예외가 위로 전파됨.

**개선**: `executor_node()`에 try/except 추가

```python
try:
    response = await model.ainvoke([HumanMessage(content=task_prompt)])
except Exception as e:
    return {
        "failed_tasks": state.get("failed_tasks", []) + [{
            "task_id": current_task["id"],
            "agent": agent_type,
            "result": "",
            "status": "failed",
            "error": str(e),
        }],
        "consecutive_failures": state.get("consecutive_failures", 0) + 1,
        "retry_count": state.get("retry_count", 0) + 1,
    }
```

---

## 8. 개선 순서 로드맵

### 지금 당장 (30분 이내)

1. `src/core/utils.py` 생성 → `extract_json()` 함수
2. `intent_router.py`와 `workflow_engine.py`의 중복 로직을 `extract_json()` 호출로 교체
3. `workflow_engine.py` 상단에 imports + 체인 상수 이동
4. `make_initial_state()` 팩토리 함수 추가

### 이번 주

5. `reviewer_node()` 프롬프트 → JSON 응답 강제
6. `check_review_result()` → JSON 파싱 방식으로 교체
7. `AgentState.completed_tasks` → `Annotated[list, operator.add]` 변경
8. `executor_node()` try/except 에러 처리 추가
9. `_MODEL_ROUTER` 모듈 레벨 싱글톤 적용

### 다음 주 (PHASE 1 시작)

10. `src/core/cost_guard.py` 구현
11. `build_orchestration_graph(checkpointer=None)` 파라미터 추가
12. `AgentState` v2 필드 추가

---

*마지막 업데이트: 2026-03-18*
