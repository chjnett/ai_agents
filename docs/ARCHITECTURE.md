# My Agent System — 완전 세부 아키텍처 & 구현 가이드

> **작성일**: 2026-03-17  
> **버전**: 0.1 (MVP)  
> **기반**: oh-my-openagent 아키텍처 학습 → Python + LangGraph로 독립 구현

> ⚡ **v2 고도화 문서 출시**: 기술 검토 피드백(Dynamic Tool Discovery, HITL, Model Routing 고도화, 병렬 실행, LangFuse, Episodic Memory)이 반영된 업그레이드 설계가 [`docs/ARCHITECTURE_V2.md`](./docs/ARCHITECTURE_V2.md)에 있습니다.
>
> ✅ **현재 구현 상태 반영 기준일**: 2026-03-19  
> PHASE 1(CostGuard, AgentState v2, Checkpointer 연동 구조)은 `ARCHITECTURE_V2.md`를 기준으로 확인하세요.

---

## 목차

1. [시스템 전체 개요](#1-시스템-전체-개요)
2. [디렉토리 구조](#2-디렉토리-구조)
3. [핵심 컴포넌트 상세](#3-핵심-컴포넌트-상세)
   - 3-1. [Intent Router (의도 분류기)](#3-1-intent-router)
   - 3-2. [Model Router (모델 선택기)](#3-2-model-router)
   - 3-3. [Workflow Engine (오케스트레이션)](#3-3-workflow-engine)
   - 3-4. [AgentState (워크플로우 상태)](#3-4-agentstate)
4. [워크플로우 실행 흐름](#4-워크플로우-실행-흐름)
   - 4-1. [Phase 0: Intent Gate](#4-1-phase-0--intent-gate)
   - 4-2. [Phase 1: Planner](#4-2-phase-1--planner)
   - 4-3. [Phase 2: Executor](#4-3-phase-2--executor)
   - 4-4. [Phase 3: Reviewer](#4-4-phase-3--reviewer)
   - 4-5. [Ralph Loop 판단](#4-5-ralph-loop-판단)
   - 4-6. [Phase 4: Finalizer](#4-6-phase-4--finalizer)
5. [라우팅 로직 상세](#5-라우팅-로직-상세)
6. [모델 배분 전략](#6-모델-배분-전략)
7. [다음 구현 단계](#7-다음-구현-단계)
8. [oh-my-openagent 대응표](#8-oh-my-openagent-대응표)
9. [개발 규칙 & 컨벤션](#9-개발-규칙--컨벤션)

---

## 1. 시스템 전체 개요

### 한 줄 설명

> **"사용자가 무엇을 원하는지 파악하고, 최적의 AI 팀을 구성해서, 완료할 때까지 자동으로 반복 실행하는 멀티-에이전트 시스템"**

### 핵심 철학 (oh-my-openagent Manifesto에서 계승)

| 원칙                             | 의미                                                   |
| -------------------------------- | ------------------------------------------------------ |
| **Human Intervention = Failure** | 사용자가 중간에 개입해야 하는 것은 시스템 실패다       |
| **Intent First**                 | 문자 그대로 실행하지 않는다. 진짜 의도를 먼저 파악한다 |
| **Right Model, Right Job**       | 모든 모델이 하나의 작업만 하는 것은 낭비다             |
| **Loop Until Done**              | 완료 조건이 달성될 때까지 절대 멈추지 않는다           |
| **Verify Before Claiming Done**  | "완료했습니다"는 검증 후에만 할 수 있다                |

### 시스템 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────────┐
│                         MY AGENT SYSTEM                             │
│                                                                     │
│  사용자 입력                                                         │
│      │                                                              │
│      ▼                                                              │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Phase 0: Intent Gate                                        │  │
│  │  "이 요청의 진짜 의도는 무엇인가?"                             │  │
│  │  research / implement / investigate / evaluate / fix / generate│  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│          ┌───────────────────┼──────────────────┐                   │
│          │                   │                  │                   │
│          ▼                   ▼                  ▼                   │
│    plan_execute          research_only        direct                │
│          │                   │                  │                   │
│          ▼                   │                  │                   │
│  ┌───────────────┐          │                  │                   │
│  │  Phase 1:     │          │                  │                   │
│  │  Planner      │          │                  │                   │
│  │  (Prometheus) │          │                  │                   │
│  └───────┬───────┘          │                  │                   │
│          │                  │                  │                   │
│          └──────────────────┴──────────────────┘                   │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Phase 2: Executor (Atlas)                                   │  │
│  │  현재 태스크를 적절한 워커 에이전트에게 위임                   │  │
│  │                                                               │  │
│  │  researcher ──┐                                               │  │
│  │  coder      ──┼── 카테고리 → 모델 자동 선택                   │  │
│  │  writer     ──┤                                               │  │
│  │  analyst    ──┘                                               │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │                                      │
│       ┌──────────────────────┤                                      │
│       │ 3회 연속 실패         │ 모든 태스크 완료                     │
│       ▼                      ▼                                      │
│  ┌─────────────┐   ┌────────────────┐                              │
│  │  Phase 3:   │   │  Loop Check    │◄─── Ralph Loop               │
│  │  Reviewer   │   │  (계속? 종료?) │                              │
│  │  (Oracle)   │   └────────┬───────┘                              │
│  └──────┬──────┘            │                                      │
│         │                   │ 계속 → Executor로 돌아감              │
│         │ approved          │ 종료 ↓                               │
│         └───────────────────┘                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Phase 4: Finalizer                                          │  │
│  │  모든 결과를 종합해서 최종 답변 생성                           │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│                              ▼                                      │
│                         사용자에게 답변                              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 디렉토리 구조

```
my-agent-system/
│
├── main.py                          # 진입점 (CLI 대화형 / 데모 모드)
├── pyproject.toml                   # 의존성 관리 (Poetry)
├── .env.example                     # 환경 변수 템플릿
├── ARCHITECTURE.md                  # 이 문서
├── README.md                        # 빠른 시작 가이드
│
├── src/
│   ├── __init__.py                  # 패키지 배럴 export
│   │
│   ├── core/                        # ★ 핵심 엔진 (현재 구현됨)
│   │   ├── __init__.py
│   │   ├── intent_router.py         # Phase 0: 의도 분류기
│   │   ├── model_router.py          # 카테고리 → 모델 자동 선택
│   │   └── workflow_engine.py       # LangGraph 오케스트레이션 + Ralph Loop
│   │
│   ├── agents/                      # ★ 에이전트 클래스 (다음 구현 단계)
│   │   ├── __init__.py
│   │   ├── base_agent.py            # 공통 추상 베이스
│   │   ├── orchestrator.py          # 메인 오케스트레이터 (Sisyphus)
│   │   ├── planner.py               # 전략 플래너 (Prometheus)
│   │   ├── reviewer.py              # 읽기 전용 리뷰어 (Oracle)
│   │   └── workers/
│   │       ├── __init__.py
│   │       ├── researcher.py        # 외부 리서치 워커
│   │       ├── coder.py             # 코딩 워커
│   │       ├── writer.py            # 글쓰기 워커
│   │       └── analyst.py           # 분석 워커
│   │
│   ├── tools/                       # ★ 재사용 가능 도구 (이후 구현)
│   │   ├── __init__.py
│   │   ├── registry.py              # 도구 등록 & 관리
│   │   ├── web_search.py            # Tavily 웹 검색
│   │   ├── code_executor.py         # Python 코드 실행
│   │   ├── file_manager.py          # 파일 읽기/쓰기
│   │   └── knowledge_base.py        # RAG 지식 베이스 검색
│   │
│   ├── hooks/                       # ★ 실행 제어 훅 (이후 구현)
│   │   ├── before_execute.py        # 실행 전 훅 (재시도, 검증)
│   │   └── after_execute.py         # 실행 후 훅 (로깅, 비용 추적)
│   │
│   ├── memory/                      # ★ 세션 & 장기 메모리 (이후 구현)
│   │   ├── session_store.py         # Redis 세션 저장
│   │   └── long_term_memory.py      # 벡터 DB 장기 기억
│   │
│   └── api/                         # ★ REST API 레이어 (이후 구현)
│       ├── routes.py                # FastAPI 라우터
│       └── models.py                # Pydantic 요청/응답 모델
│
├── config/
│   ├── agents.yaml                  # 에이전트 기본 설정
│   └── models.yaml                  # 모델 매핑 커스터마이징
│
└── tests/
    ├── __init__.py
    ├── test_core.py                 # Intent Router, Model Router, Loop 테스트
    ├── test_agents.py               # 에이전트 단위 테스트 (이후 추가)
    └── test_e2e.py                  # 엔드-투-엔드 통합 테스트 (이후 추가)
```

---

## 3. 핵심 컴포넌트 상세

### 3-1. Intent Router

**파일**: `src/core/intent_router.py`  
**역할**: 모든 사용자 요청이 통과하는 첫 번째 관문. 요청의 **진짜 의도**를 파악한다.

#### 의도 타입 분류표

| IntentType    | 트리거 키워드                                       | 권장 워크플로우 | 사용 모델           |
| ------------- | --------------------------------------------------- | --------------- | ------------------- |
| `research`    | "explain", "how does", "what is", "이해", "알려줘"  | `research_only` | Claude Haiku (빠름) |
| `implement`   | "create", "add", "implement", "만들어", "구현해"    | `plan_execute`  | Planner → Deep 모델 |
| `investigate` | "look into", "check", "analyze", "분석해", "조사해" | `direct`        | Analysis 모델       |
| `evaluate`    | "what do you think", "review", "평가해", "의견"     | `direct`        | Ultrabrain 모델     |
| `fix`         | "error", "broken", "not working", "오류", "고쳐"    | `plan_execute`  | Deep 모델           |
| `generate`    | "write a report", "summarize", "draft", "작성해"    | `direct`        | Creative 모델       |

#### 반환 데이터 구조 (`RoutingDecision`)

```python
class RoutingDecision(BaseModel):
    intent: IntentType          # 분류된 의도
    confidence: float           # 확신도 0.0~1.0
    reasoning: str              # 분류 이유 한 줄 설명
    recommended_workflow: str   # 실행할 워크플로우 타입
    suggested_agents: list[str] # 권장 에이전트 목록
```

#### 분류 실패 처리

LLM이 JSON을 제대로 반환하지 못한 경우, **기본값(research + research_only)**으로 안전하게 폴백한다. 절대 예외를 던지지 않는다.

#### 모델 선택 이유

| 모델               | 이유                                                                       |
| ------------------ | -------------------------------------------------------------------------- |
| `claude-haiku-4-5` | 분류처럼 단순 작업에는 가장 빠르고 저렴한 모델 사용 (oh-my-openagent 원칙) |

---

### 3-2. Model Router

**파일**: `src/core/model_router.py`  
**역할**: 태스크 카테고리에 따라 가장 적합한 LLM을 자동으로 선택한다.

#### 카테고리-모델 매핑

```
TaskCategory.QUICK      → claude-haiku-4-5    (빠르고 저렴, 단순 작업)
TaskCategory.DEEP       → claude-opus-4-6     (깊은 생각 필요, 코딩/아키텍처)
TaskCategory.VISUAL     → gemini-2.5-pro      (시각/UI 특화, Gemini가 이미지에 강함)
TaskCategory.ULTRABRAIN → gpt-4o              (최고 난이도 추론, GPT가 논리에 강함)
TaskCategory.CREATIVE   → claude-sonnet-4-6   (창작/글쓰기, Claude가 문장에 강함)
TaskCategory.ANALYSIS   → gpt-4o              (데이터 분석, GPT가 패턴 인식에 강함)
```

#### 의도 → 카테고리 매핑

```
research    → QUICK      (정보 수집은 빠른 모델로 충분)
implement   → DEEP       (구현은 심층 모델이 필요)
investigate → ANALYSIS   (분석은 분석 특화 모델)
evaluate    → ULTRABRAIN (평가는 최고 추론 모델)
fix         → DEEP       (수정은 코드를 깊이 이해해야)
generate    → CREATIVE   (생성은 글쓰기 특화 모델)
```

#### 커스터마이징

```python
# 기본 사용
router = ModelRouter()

# 모델 오버라이드
router = ModelRouter(overrides={
    "quick":      "claude-sonnet-4-6",  # 더 고품질로
    "ultrabrain": "claude-opus-4-6",    # GPT 대신 Claude 사용
})
```

---

### 3-3. Workflow Engine

**파일**: `src/core/workflow_engine.py`  
**역할**: LangGraph `StateGraph`로 전체 에이전트 오케스트레이션을 구현한다.

#### LangGraph 노드 & 엣지 구조

```
노드(Node)   = 실행 단위 (각 Phase)
엣지(Edge)   = 노드 간 이동 경로
조건부 엣지  = 상태에 따라 다른 노드로 분기
```

#### 등록된 노드 목록

| 노드 이름     | 함수                 | Phase | 역할                                       |
| ------------- | -------------------- | ----- | ------------------------------------------ |
| `intent_gate` | `intent_gate_node()` | 0     | 의도 분류 + 워크플로우 결정                |
| `planner`     | `planner_node()`     | 1     | 실행 계획 수립 (plan_execute 워크플로우만) |
| `executor`    | `executor_node()`    | 2     | 태스크 실행 (워커 에이전트 호출)           |
| `reviewer`    | `reviewer_node()`    | 3     | 결과 품질 검토                             |
| `loop_check`  | `lambda s: s`        | -     | 상태 통과 (Ralph Loop 판단 직전)           |
| `finalizer`   | `finalizer_node()`   | 4     | 최종 답변 합성                             |

#### 조건부 엣지 라우팅 함수

| 함수                       | 입력         | 출력 가능값                               | 판단 기준                 |
| -------------------------- | ------------ | ----------------------------------------- | ------------------------- |
| `route_by_intent()`        | `AgentState` | `"planner"`, `"executor"`                 | `recommended_workflow` 값 |
| `check_execution_result()` | `AgentState` | `"reviewer"`, `"executor"`, `"finalizer"` | 완료율, 실패 횟수         |
| `check_review_result()`    | `AgentState` | `"loop_check"`, `"executor"`, `"planner"` | 리뷰어 응답 내용          |
| `should_continue_loop()`   | `AgentState` | `"executor"`, `"finalizer"`               | Ralph Loop 완료 판단      |

---

### 3-4. AgentState
    
**파일**: `src/core/workflow_engine.py`  
**역할**: LangGraph 전체 워크플로우의 **공유 상태**. 모든 노드가 읽고 쓴다.

#### 상태 필드 전체 설명

```python
class AgentState(TypedDict):

    # ── 기본 요청 정보 ──────────────────────────────────────
    messages: list[BaseMessage]   # 전체 대화 히스토리 (자동 누적)
    user_request: str             # 사용자의 원본 요청 텍스트 (변경 불가)
    session_id: str               # 세션 고유 ID (UUID)

    # ── Intent Gate 결과 ─────────────────────────────────────
    intent: str                   # IntentType ("research", "implement", ...)
    recommended_workflow: str     # "plan_execute" | "direct" | "research_only"

    # ── Planner 결과 (plan_execute 워크플로우만 채워짐) ──────
    plan: list[TaskItem] | None   # 태스크 목록 (순서 중요)
    acceptance_criteria: list[str] # 완료 판단 기준 목록

    # ── 실행 추적 ────────────────────────────────────────────
    current_task_index: int       # 현재 실행 중인 태스크 인덱스
    completed_tasks: list[TaskResult]  # 완료된 태스크 + 결과
    failed_tasks: list[TaskResult]     # 실패한 태스크 + 에러

    # ── Ralph Loop 상태 ──────────────────────────────────────
    loop_active: bool             # False이면 루프 즉시 종료
    loop_iteration: int           # 현재 반복 횟수 (1부터 시작)
    max_loop_iterations: int      # 최대 반복 한도 (기본 10)

    # ── 에러 복구 ────────────────────────────────────────────
    retry_count: int              # 전체 재시도 횟수 (5 초과 → 강제 종료)
    consecutive_failures: int     # 연속 실패 횟수 (3 초과 → Reviewer 호출)

    # ── 최종 결과 ────────────────────────────────────────────
    final_answer: str | None      # 사용자에게 전달할 최종 답변
    workflow_trace: list[str]     # 실행된 노드 이름 순서 (디버깅용)
```

#### TaskItem 구조

```python
class TaskItem(TypedDict):
    id: str                # "task-01", "task-02", ...
    title: str             # 태스크 제목 (한 줄)
    description: str       # 상세 설명 (무엇을 정확히 해야 하는가)
    agent: str             # "researcher" | "coder" | "writer" | "analyst"
    depends_on: list[str]  # 선행 태스크 ID (["task-01"])
    success_criteria: str  # 완료 검증 기준
    status: str            # "pending" | "in_progress" | "done" | "failed"
```

#### TaskResult 구조

```python
class TaskResult(TypedDict):
    task_id: str           # 완료된 TaskItem의 ID
    agent: str             # 실행한 에이전트 타입
    result: str            # 에이전트가 생성한 결과물 (전문)
    status: str            # "success" | "failed"
    error: str | None      # 실패 시 에러 메시지
```

---

## 4. 워크플로우 실행 흐름

### 4-1. Phase 0 — Intent Gate

**노드**: `intent_gate`  
**함수**: `intent_gate_node()`

```
실행 순서:
1. IntentRouter.classify(user_request) 호출
2. Claude Haiku가 JSON으로 의도 분류
3. AgentState에 intent + recommended_workflow 저장
4. workflow_trace에 "intent_gate" 추가
5. → route_by_intent()로 분기
```

**분기 결과**:
- `plan_execute` → `planner` 노드로 이동
- `direct` 또는 `research_only` → `executor` 노드로 이동

---

### 4-2. Phase 1 — Planner

**노드**: `planner`  
**함수**: `planner_node()`  
**실행 조건**: `recommended_workflow == "plan_execute"` 일 때만

```
실행 순서:
1. Claude Opus에게 태스크 계획 수립 요청
2. JSON 형태의 tasks[] + acceptance_criteria[] 반환
3. AgentState.plan에 저장
4. current_task_index = 0으로 초기화
5. → executor 노드로 이동 (항상)
```

**플래너 프롬프트 구조**:
```
- User request: <원본 요청>
- Intent type: <분류된 의도>
- 출력: tasks (id, title, description, agent, depends_on, success_criteria)
- 제약: 최대 7개 태스크, 각 태스크는 원자적(하나의 명확한 행동)
```

**왜 Claude Opus인가?**: 계획 수립은 가장 중요한 단계. 여기서 잘못되면 모든 것이 잘못됨. 비용을 아끼지 않는다.

---

### 4-3. Phase 2 — Executor

**노드**: `executor`  
**함수**: `executor_node()`

#### Case A: 계획이 있는 경우 (plan_execute 워크플로우)

```
실행 순서:
1. plan[current_task_index] 현재 태스크 선택
2. task.agent 타입으로 TaskCategory 결정
   - researcher → QUICK  → Claude Haiku
   - coder      → DEEP   → Claude Opus
   - writer     → CREATIVE → Claude Sonnet
   - analyst    → ANALYSIS → GPT-4o
3. ModelRouter.get_model(category)로 LLM 선택
4. 태스크 실행 → TaskResult 생성
5. completed_tasks에 결과 추가
6. current_task_index += 1
7. loop_iteration += 1
8. → check_execution_result()로 분기
```

#### Case B: 계획이 없는 경우 (direct / research_only 워크플로우)

```
실행 순서:
1. ModelRouter.get_model_for_intent(intent)로 모델 선택
2. user_request를 바로 LLM에 전달
3. 응답을 final_answer에 저장
4. loop_active = False로 루프 종료
5. → finalizer 노드로 이동
```

---

### 4-4. Phase 3 — Reviewer

**노드**: `reviewer`  
**함수**: `reviewer_node()`  
**실행 조건**: 모든 태스크 완료 OR 3회 연속 실패 시

```
실행 순서:
1. completed_tasks를 요약
2. GPT-4o에게 검토 요청
   - "사용자 원래 요청이 충족되었는가?"
   - "무엇이 빠졌는가?"
   - "approved | need_fix | replan 중 하나"
3. → check_review_result()로 분기
```

**분기 결과**:
- `approved` → `loop_check`
- `need_fix` → `executor` (수정 실행)
- `replan` → `planner` (계획 재수립)

**왜 GPT-4o인가?**: 검토는 자신이 만든 결과를 다른 시각에서 봐야 함. Claude가 만든 것을 GPT가 검토하면 더 객관적. (oh-my-openagent의 Oracle patternr)

---

### 4-5. Ralph Loop 판단

**노드**: `loop_check` (통과 노드)  
**함수**: `should_continue_loop()`

```
판단 로직 (순서대로):

IF loop_iteration >= max_loop_iterations (기본 10):
    → "finalizer"  # 무한 루프 방지 안전장치

IF NOT loop_active:
    → "finalizer"  # 명시적 종료 신호

IF completed_tasks 개수 < plan 태스크 총 수:
    → "executor"   # 아직 할 일이 있음

ELSE:
    → "finalizer"  # 모든 태스크 완료
```

**Ralph Loop 핵심 원칙**: "완료했다고 선언하기 전에 반드시 검증하라." 이 함수가 `finalizer`를 반환할 때만 작업이 진짜 끝난다.

---

### 4-6. Phase 4 — Finalizer

**노드**: `finalizer`  
**함수**: `finalizer_node()`

```
실행 순서:
1. 이미 final_answer가 있으면 → 그대로 반환
2. completed_tasks 전체 결과를 하나로 합침
3. Claude Sonnet에게 최종 답변 합성 요청
4. final_answer 저장
5. loop_active = False
6. → END
```

**왜 Claude Sonnet인가?**: 최종 답변은 사용자에게 전달되는 최종 산출물. Haiku보다 품질이 중요하지만 Opus처럼 비용을 낭비할 필요는 없음.

---

## 5. 라우팅 로직 상세

### 전체 라우팅 결정 트리

```
사용자 입력
    │
    ▼
[intent_gate_node]
    │
    ├─ recommended_workflow == "plan_execute"
    │       → planner → executor
    │
    └─ recommended_workflow == "direct" | "research_only"
            → executor (계획 없이 바로)

[executor_node 완료 후]
    │
    ├─ consecutive_failures >= 3
    │       → reviewer (긴급 검토 요청)
    │
    ├─ retry_count >= 5
    │       → finalizer (강제 종료)
    │
    ├─ completed >= total (모든 태스크 완료)
    │       → reviewer
    │
    └─ else
            → executor (다음 태스크 실행)

[reviewer_node 완료 후]
    │
    ├─ "replan" 키워드 감지
    │       → planner (재계획)
    │
    ├─ "fix" | "need_fix" 키워드 감지
    │       → executor (수정)
    │
    └─ else
            → loop_check

[loop_check]
    │
    ├─ iteration >= max (기본 10)  → finalizer
    ├─ loop_active == False         → finalizer
    ├─ 미완료 태스크 존재           → executor
    └─ 모든 태스크 완료             → finalizer
```

### 에러 복구 전략 (oh-my-openagent Phase 2C 계승)

```
1회~2회 실패: executor가 자체 재시도
3회 연속 실패: reviewer(Oracle)에게 상담 요청
5회 총 재시도: 강제 finalizer로 이동 + 실패 이유 포함 답변
```

---

## 6. 모델 배분 전략

### 노드별 모델 선택 이유

| 단계        | 노드                 | 선택한 모델         | 이유                                 |
| ----------- | -------------------- | ------------------- | ------------------------------------ |
| 의도 분류   | intent_gate          | `claude-haiku-4-5`  | 단순 분류 → 최저비용                 |
| 계획 수립   | planner              | `claude-opus-4-6`   | 계획 품질이 전체를 결정 → 최고품질   |
| 리서치 실행 | executor(researcher) | `claude-haiku-4-5`  | 정보 수집은 속도가 중요              |
| 코딩 실행   | executor(coder)      | `claude-opus-4-6`   | 코드는 깊은 이해 필요                |
| 글쓰기 실행 | executor(writer)     | `claude-sonnet-4-6` | 창작은 Sonnet이 균형적               |
| 분석 실행   | executor(analyst)    | `gpt-4o`            | 데이터 분석은 GPT가 강함             |
| 검토        | reviewer             | `gpt-4o`            | Claude 결과를 GPT가 검토 → 교차 검증 |
| 최종 합성   | finalizer            | `claude-sonnet-4-6` | 품질 vs 비용 균형                    |

### 비용 최적화 원칙

```
빠른 모델 (Haiku): 분류, 단순 질문, 정보 수집
중간 모델 (Sonnet): 글쓰기, 최종 합성
비싼 모델 (Opus, GPT-4o): 계획, 코딩, 검토 (품질이 필수인 경우만)
```

---

## 7. 다음 구현 단계

### Step 1: 에이전트 클래스 분리 (현재 executor_node 내 인라인 로직 분리)

**파일**: `src/agents/base_agent.py`

```python
# 구현할 내용:
# - BaseAgent 추상 클래스 (name, description, category, cost 속성)
# - run(task: str, context: dict) → dict 추상 메서드
# - with_retry, log_execution 데코레이터 적용
```

**파일**: `src/agents/workers/researcher.py`

```python
# 구현할 내용:
# - ResearcherAgent(BaseAgent) 구체 클래스
# - web_search 도구 연결
# - 리서치 특화 시스템 프롬프트
# - 결과 포맷: {"sources": [...], "summary": "..."}
```

**파일**: `src/agents/workers/coder.py`

```python
# 구현할 내용:
# - CoderAgent(BaseAgent) 구체 클래스
# - code_executor 도구 연결 (코드 실행 + 검증)
# - 코딩 특화 시스템 프롬프트
# - 결과 포맷: {"code": "...", "explanation": "...", "tests": "..."}
```

---

### Step 2: Tool Registry 구현

**파일**: `src/tools/registry.py`

```python
# 구현할 내용:
# - ToolRegistry 클래스 (도구 등록/조회)
# - 에이전트가 필요한 도구를 이름으로 요청 가능
# - 도구별 사용 통계 수집

# 등록할 도구:
# - web_search (Tavily API)
# - code_executor (subprocess 또는 e2b sandbox)
# - file_manager (파일 읽기/쓰기)
# - knowledge_base (ChromaDB RAG)
```

---

### Step 3: FastAPI REST API

**파일**: `src/api/routes.py`

```python
# 구현할 엔드포인트:
# POST /api/chat           → 단일 요청 처리
# POST /api/chat/stream    → SSE 스트리밍 응답
# GET  /api/sessions/{id}  → 세션 상태 조회
# DELETE /api/sessions/{id} → 세션 종료

# Pydantic 모델:
# - ChatRequest(message, session_id, stream, max_iterations)
# - ChatResponse(session_id, intent, workflow_trace, result, cost_estimate)
```

---

### Step 4: Redis 세션 저장

**파일**: `src/memory/session_store.py`

```python
# 구현할 내용:
# - AgentState를 Redis에 JSON 직렬화 저장
# - 세션 ID로 이전 상태 복원 (세션 연속성)
# - TTL 설정 (기본 24시간)
# - LangGraph checkpointer 연동
```

---

### Step 5: LangFuse 통합 (관찰 가능성)

이전 프로젝트에서 사용한 LangFuse 경험 재활용.

```python
# src/hooks/after_execute.py

from langfuse.langchain import CallbackHandler

# 각 에이전트 실행마다:
# - 입력 토큰 수
# - 출력 토큰 수
# - 비용 (모델별 단가 × 토큰 수)
# - 실행 시간
# - 성공/실패 여부
```

---

### Step 6: RAG Knowledge Base 통합

이전 Docker RAG 프로젝트 경험 재활용.

```python
# src/tools/knowledge_base.py

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

# 워크플로우:
# 1. 문서 → 임베딩 → ChromaDB 저장
# 2. 사용자 질문 → 유사 문서 검색
# 3. 검색 결과 → Researcher Agent 컨텍스트에 주입
```

---

## 8. oh-my-openagent 대응표

현재 구현된 Python 시스템과 원본 TypeScript 시스템의 1:1 대응.

| oh-my-openagent (TypeScript)        | My Agent System (Python)                            | 파일 위치                     |
| ----------------------------------- | --------------------------------------------------- | ----------------------------- |
| `Phase 0 - Intent Gate`             | `IntentRouter.classify()`                           | `src/core/intent_router.py`   |
| `Phase 1 - Codebase Assessment`     | `planner_node()`                                    | `src/core/workflow_engine.py` |
| `Phase 2A - Exploration & Research` | `executor_node(agent="researcher")`                 | `src/core/workflow_engine.py` |
| `Phase 2B - Implementation`         | `executor_node(agent="coder")`                      | `src/core/workflow_engine.py` |
| `Phase 2C - Failure Recovery`       | `check_execution_result()` + `consecutive_failures` | `src/core/workflow_engine.py` |
| `Phase 3 - Completion`              | `finalizer_node()`                                  | `src/core/workflow_engine.py` |
| `DEFAULT_CATEGORIES`                | `TaskCategory` + `MODEL_CATEGORY_MAPPING`           | `src/core/model_router.py`    |
| `loop-state-controller.ts`          | `should_continue_loop()`                            | `src/core/workflow_engine.py` |
| `ralph-loop-hook.ts`                | `loop_check` 노드 + Ralph Loop 엣지                 | `src/core/workflow_engine.py` |
| `AgentConfig`                       | `AgentState` TypedDict                              | `src/core/workflow_engine.py` |
| `createOracleAgent()`               | `reviewer_node()`                                   | `src/core/workflow_engine.py` |
| `createSisyphusAgent()`             | `build_orchestration_graph()`                       | `src/core/workflow_engine.py` |
| `AgentPromptMetadata`               | `TaskItem` + `TaskResult`                           | `src/core/workflow_engine.py` |
| `createXXXHook()`                   | Python 데코레이터                                   | `src/hooks/` (예정)           |
| `comment-checker hook`              | ruff linter + 코드 리뷰 훅                          | (예정)                        |
| `session_id` 연속성                 | Redis + LangGraph checkpointer                      | (예정)                        |

---

## 9. 개발 규칙 & 컨벤션

oh-my-openagent의 컨벤션을 Python에 맞게 적용.

### 필수 규칙

```
✅ Poetry만 사용 (pip 직접 사용 금지)
✅ Python 3.11+ (타입 힌트 최신 문법)
✅ Pydantic v2 (데이터 검증)
✅ 모든 비동기 함수는 async/await
✅ 타입 힌트 100% (str | None, list[str] 등)
✅ 테스트는 given/when/then 패턴
✅ 각 모듈은 200줄 이하 (oh-my-openagent soft limit 계승)
```

### 네이밍 컨벤션

```
파일:     snake_case      (intent_router.py, model_router.py)
클래스:   PascalCase      (IntentRouter, ModelRouter)
함수:     snake_case      (classify(), get_model())
상수:     UPPER_SNAKE     (MODEL_CATEGORY_MAPPING, DEFAULT_MAX_ITER)
노드함수: snake_case_node (intent_gate_node, planner_node)
```

### 금지 패턴

```
❌ 타입 힌트 없는 함수 선언
❌ except: pass (에러를 무시하는 빈 except)
❌ utils.py, helpers.py 같은 catch-all 파일
❌ God object (너무 많은 역할을 가진 단일 클래스)
❌ 하드코딩된 API 키 (반드시 환경 변수)
❌ 동기 코드로 비동기 API 호출 (asyncio.run 남발)
```

### 테스트 패턴 (given/when/then)

```python
class TestIntentRouter:
    class TestResearchIntent:
        async def test_how_does_x_work_is_research(self, router):
            # given
            request = "how does Redis work?"
            # when
            result = await router.classify(request)
            # then
            assert result.intent == IntentType.RESEARCH
```

### 커밋 메시지

```
feat: add researcher agent with web search tool
fix: handle JSON parse failure in intent_router
test: add loop continuation unit tests
refactor: extract planner prompt to constants
docs: update architecture guide with new routing logic
```

---

*마지막 업데이트: 2026-03-17*
