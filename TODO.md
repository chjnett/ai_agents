# TODO — My Agent System

> **기준일**: 2026-03-18  
> **참고 문서**: `docs/ARCHITECTURE_V2.md`  
> `✅ 완료` · `🔨 진행 중` · `⬜ 미구현`

---

## 현재 구현 현황 (v0.1 MVP)

| 파일                          | 상태 | 설명                                                             |
| ----------------------------- | ---- | ---------------------------------------------------------------- |
| `src/core/intent_router.py`   | ✅    | IntentType 6종, RoutingDecision, Claude Haiku 분류기             |
| `src/core/model_router.py`    | ✅    | TaskCategory 6종, 카테고리→모델 매핑, 의도→카테고리 매핑         |
| `src/core/workflow_engine.py` | ✅    | LangGraph 6노드, Ralph Loop, 라우팅 함수 4종                     |
| `main.py`                     | ✅    | 대화형 CLI + 데모 모드                                           |
| `tests/test_core.py`          | ✅    | IntentRouter / ModelRouter / Loop 단위 테스트                    |
| `pyproject.toml`              | ✅    | v0.2 의존성 정의 (langfuse, chromadb, langgraph-checkpoint 포함) |
| `.gitignore`                  | ✅    | 프로젝트 스택 맞춤 (SQLite, ChromaDB, LangFuse, .env 등)         |
| `docs/ARCHITECTURE_V2.md`     | ✅    | v2 고도화 설계 문서 (813줄)                                      |

---

## PHASE 1 — 안전장치 & 상태 영속성 🚨 Blocker

> 이 단계 없이는 루프가 폭주하거나 세션이 끊기면 복구 불가

### 1-1. CostGuard (비용 하드캡)
- **파일**: `src/core/cost_guard.py` ⬜
- [ ] `CostGuard` 클래스 구현
  - [ ] 모델별 단가 테이블 (`PRICE_PER_1K`)
  - [ ] `record(model, input_tokens, output_tokens)` 메서드
  - [ ] `is_over_limit()` 판단 메서드
  - [ ] `summary()` 리포트 메서드
- [ ] `AgentState`에 비용 추적 필드 추가
  - [ ] `total_cost_usd: float`
  - [ ] `total_tokens: int`
  - [ ] `max_cost_usd: float` (기본 $1.0)
  - [ ] `max_tokens: int` (기본 500,000)
- [ ] `should_continue_loop()`에 비용 초과 조건 추가
- [ ] `executor_node()`에서 매 LLM 호출 후 `CostGuard.record()` 호출

### 1-2. LangGraph Checkpointer (세션 영속성)
- **파일**: `main.py` 수정 ⬜
- [ ] `SqliteSaver` 체크포인터 연결
  ```python
  from langgraph.checkpoint.sqlite import SqliteSaver
  checkpointer = SqliteSaver.from_conn_string("checkpoints.db")
  graph = build_orchestration_graph(checkpointer=checkpointer)
  ```
- [ ] `config = {"configurable": {"thread_id": session_id}}` 패턴 적용
- [ ] 세션 재개 (`Command(resume=...)`) 로직 추가
- [ ] `build_orchestration_graph(checkpointer=...)` 파라미터 수용하도록 수정

### 1-3. AgentState v2 필드 추가
- **파일**: `src/core/workflow_engine.py` 수정 ⬜
- [ ] `user_id: str | None` 추가
- [ ] `task_complexity: str` 추가 (`"low" | "medium" | "high"`)
- [ ] `parallel_groups: list[list[str]] | None` 추가
- [ ] `require_approval: bool` 추가
- [ ] `total_cost_usd`, `total_tokens`, `max_cost_usd`, `max_tokens` 추가
- [ ] `past_episodes: list[dict] | None` 추가
- [ ] `user_preferences: dict` 추가
- [ ] `completed_tasks`, `failed_tasks`, `workflow_trace` → `Annotated[list, operator.add]`로 변경 (병렬 실행 준비)

---

## PHASE 2 — 에이전트 클래스 분리

> 현재 executor_node() 안에 인라인된 로직을 전용 클래스로 분리

### 2-1. BaseAgent
- **파일**: `src/agents/base_agent.py` ⬜
- [ ] `BaseAgent` 추상 클래스
  - [ ] `name: str`, `description: str`, `category: str`, `cost: str` 속성
  - [ ] `run(task: str, context: dict) → dict` 추상 메서드
  - [ ] `get_metadata() → dict` 공통 메서드
- [ ] `with_retry(max_retries)` 데코레이터
- [ ] `log_execution` 데코레이터 (실행 전후 로깅)
- [ ] `validate_output(schema)` 데코레이터 (Pydantic 출력 검증)

### 2-2. Worker Agents
- **파일**: `src/agents/workers/` ⬜

#### ResearcherAgent
- **파일**: `src/agents/workers/researcher.py` ⬜
- [ ] `ResearcherAgent(BaseAgent)` 구현
- [ ] 시스템 프롬프트: 리서치 특화 (출처 명시, 요약 형태)
- [ ] 결과 포맷: `{"sources": [...], "summary": "..."}`
- [ ] `web_search` 도구 연결 (동적 주입 준비)

#### CoderAgent
- **파일**: `src/agents/workers/coder.py` ⬜
- [ ] `CoderAgent(BaseAgent)` 구현
- [ ] 시스템 프롬프트: 코드 품질, 에러 핸들링, 테스트 명시
- [ ] 결과 포맷: `{"code": "...", "explanation": "...", "tests": "..."}`
- [ ] `code_executor` 도구 연결 (실행 + 검증)

#### WriterAgent
- **파일**: `src/agents/workers/writer.py` ⬜
- [ ] `WriterAgent(BaseAgent)` 구현
- [ ] 시스템 프롬프트: 구조화된 문체, 마크다운 형식
- [ ] 결과 포맷: `{"content": "...", "word_count": 0}`

#### AnalystAgent
- **파일**: `src/agents/workers/analyst.py` ⬜
- [ ] `AnalystAgent(BaseAgent)` 구현
- [ ] 시스템 프롬프트: 데이터 기반 판단, 수치 인용
- [ ] 결과 포맷: `{"findings": [...], "conclusion": "..."}`

### 2-3. executor_node() 리팩터링
- **파일**: `src/core/workflow_engine.py` 수정 ⬜
- [ ] 인라인 LLM 호출 → `WorkerAgent.run()` 호출로 교체
- [ ] `AGENT_REGISTRY: dict[str, BaseAgent]` 싱글톤 관리

---

## PHASE 3 — Dynamic Tool Discovery

> 고정 도구 할당 → 시맨틱 유사도 기반 동적 주입

### 3-1. Tool 구현체
- **파일**: `src/tools/` ⬜

| 파일                      | 도구                              | 상태 |
| ------------------------- | --------------------------------- | ---- |
| `tools/web_search.py`     | `web_search` (Tavily)             | ⬜    |
| `tools/code_executor.py`  | `code_executor` (subprocess)      | ⬜    |
| `tools/file_manager.py`   | `file_read`, `file_write`         | ⬜    |
| `tools/knowledge_base.py` | `knowledge_search` (ChromaDB RAG) | ⬜    |
| `tools/vision.py`         | `vision_analyzer` (Gemini Vision) | ⬜    |

- [ ] 각 도구를 `@tool` 데코레이터로 정의
- [ ] 도구 `description`을 임베딩에 최적화된 텍스트로 작성

### 3-2. ToolRegistry
- **파일**: `src/tools/registry.py` ⬜
- [ ] `ToolRegistry` 클래스
  - [ ] `register(tool: BaseTool)` — ChromaDB에 임베딩 저장
  - [ ] `find_relevant(task, top_k=4)` — 시맨틱 유사도 검색
  - [ ] `get_all()` — 전체 도구 반환
- [ ] 앱 시작 시 기본 도구 6종 자동 등록
- [ ] `executor_node()`에서 `registry.find_relevant(task)` 호출로 교체

---

## PHASE 4 — Model Routing 고도화 (2단계)

> 카테고리 × 복잡도 매트릭스로 과도한 고비용 모델 사용 방지

### 4-1. ComplexityLevel & MODEL_MATRIX
- **파일**: `src/core/model_router.py` 수정 ⬜
- [ ] `ComplexityLevel` Enum 추가 (`LOW / MEDIUM / HIGH`)
- [ ] `MODEL_MATRIX: dict[tuple[TaskCategory, ComplexityLevel], str]` 구현
  - [ ] DEEP × 3단계 (Haiku / Sonnet / Opus)
  - [ ] ULTRABRAIN × 3단계 (gpt-4o-mini / gpt-4o / gpt-4o)
  - [ ] QUICK × 3단계
  - [ ] CREATIVE × 3단계
  - [ ] ANALYSIS × 3단계
- [ ] `estimate_complexity(task_description) → ComplexityLevel` 규칙 기반 함수
- [ ] `get_model_v2(category, task_description)` 메서드 추가
- [ ] 기존 `get_model()` deprecated 처리 후 v2로 교체

---

## PHASE 5 — Human-in-the-Loop (HITL)

> 비가역적 작업(파일 쓰기, 외부 API) 전 사용자 승인

### 5-1. Interrupt 적용
- **파일**: `src/core/workflow_engine.py` 수정 ⬜
- [ ] `from langgraph.types import interrupt` import
- [ ] `planner_node()`에 `interrupt()` Breakpoint 추가
  - [ ] `require_approval == True`일 때만 발동
  - [ ] `approve` → 계속 실행
  - [ ] `modify: <지시>` → `_replan_with_feedback()` 호출
  - [ ] `cancel` → 루프 종료
- [ ] `executor_node()`에 위험 태스크 확인 추가
  - [ ] `RISKY_AGENTS = {"file_writer", "api_caller", "coder"}` 정의
  - [ ] 위험 에이전트 실행 전 `interrupt()` 발동

### 5-2. CLI HITL 핸들러
- **파일**: `main.py` 수정 ⬜
- [ ] `interrupt` 상태 감지 후 사용자 입력 대기
- [ ] `Command(resume=user_input)` 로 재개 로직 구현

---

## PHASE 6 — Observability (LangFuse)

> 모든 LLM 호출을 추적 → 병목·비용·에러 가시화

### 6-1. LangFuse 트레이서
- **파일**: `src/observability/langfuse_tracer.py` ⬜
- [ ] `Langfuse` 클라이언트 초기화 (환경 변수 기반)
- [ ] `create_session_tracer(session_id) → CallbackHandler`
- [ ] `NodeTimingCallback` 구현
  - [ ] `on_llm_start()` → 시작 시간 기록
  - [ ] `on_llm_end()` → 실행시간 + 토큰 LangFuse에 전송

### 6-2. 각 노드에 콜백 적용
- **파일**: `src/core/workflow_engine.py` 수정 ⬜
- [ ] `intent_gate_node()` — 트레이서 적용
- [ ] `planner_node()` — 트레이서 적용
- [ ] `executor_node()` — 트레이서 + 타이밍 콜백 적용
- [ ] `reviewer_node()` — 트레이서 적용
- [ ] `finalizer_node()` — 트레이서 적용

---

## PHASE 7 — 병렬 실행

> depends_on 없는 태스크는 동시 실행 → 전체 처리 시간 단축

### 7-1. 병렬 처리 유틸
- **파일**: `src/core/workflow_engine.py` 수정 ⬜
- [ ] `get_parallel_groups(plan) → list[list[TaskItem]]` 구현
  - [ ] BFS 기반 의존성 위상 정렬
  - [ ] 순환 의존성 감지 후 예외 처리
- [ ] `parallel_dispatcher(state) → list[Send]` 구현
  - [ ] `from langgraph.graph import Send` 활용
  - [ ] ready 태스크만 선별해서 동시 전송
- [ ] `single_task_executor(state) → dict` 병렬 워커 노드 구현
- [ ] `merge_results(state) → dict` 취합 노드 구현
- [ ] `build_orchestration_graph()`에 병렬 노드 등록 및 엣지 추가

---

## PHASE 8 — 메모리 시스템

### 8-1. Session Memory (Layer 2 — Redis)
- **파일**: `src/memory/session_store.py` ⬜
- [ ] `SessionStore` 클래스
  - [ ] `save(session_id, state)` — JSON 직렬화 → Redis
  - [ ] `load(session_id) → AgentState | None` — Redis 역직렬화
  - [ ] TTL 24시간 자동 설정
- [ ] `AgentState` 직렬화 헬퍼 (TypedDict → JSON)

### 8-2. Episodic Memory (Layer 3 — ChromaDB)
- **파일**: `src/memory/episodic_memory.py` ⬜
- [ ] `Episode` Pydantic 모델 구현
  - [ ] 필드: `episode_id`, `intent`, `user_request_summary`, `successful_plan` 등
- [ ] `EpisodicMemory` 클래스
  - [ ] `save_episode(state)` — `finalizer_node()` 완료 후 자동 호출
  - [ ] `recall(task, top_k=3) → list[Episode]` — 유사 경험 검색
- [ ] `planner_node()`에서 `recall()` 호출 후 프롬프트에 주입

---

## PHASE 9 — REST API & 스트리밍

### 9-1. FastAPI 레이어
- **파일**: `src/api/` ⬜
- [ ] `src/api/models.py` — Pydantic 요청/응답 모델
  - [ ] `ChatRequest(message, session_id, stream, max_cost_usd, require_approval)`
  - [ ] `ChatResponse(session_id, intent, workflow_trace, result, cost_summary)`
- [ ] `src/api/routes.py` — FastAPI 라우터
  - [ ] `POST /api/chat` — 단일 요청
  - [ ] `POST /api/chat/stream` — SSE 스트리밍
  - [ ] `GET /api/sessions/{id}` — 세션 상태 조회
  - [ ] `DELETE /api/sessions/{id}` — 세션 종료
  - [ ] `POST /api/sessions/{id}/resume` — HITL 재개

### 9-2. SSE 스트리밍
- **파일**: `src/api/routes.py` ⬜
- [ ] `graph.astream_events()` 활용
- [ ] 노드 완료마다 SSE 이벤트 발행
- [ ] 클라이언트에서 실시간 진행 상황 확인 가능

---

## PHASE 10 — 테스트 보강

| 테스트 파일                | 대상                                 | 상태          |
| -------------------------- | ------------------------------------ | ------------- |
| `tests/test_core.py`       | IntentRouter, ModelRouter, Loop 로직 | ✅ 기본 작성됨 |
| `tests/test_agents.py`     | Worker 에이전트 단위 테스트          | ⬜             |
| `tests/test_tools.py`      | 각 도구 단위 테스트                  | ⬜             |
| `tests/test_memory.py`     | SessionStore, EpisodicMemory         | ⬜             |
| `tests/test_cost_guard.py` | CostGuard 상한선 테스트              | ⬜             |
| `tests/test_e2e.py`        | 전체 워크플로우 통합 테스트          | ⬜             |

- [ ] `test_core.py` — `ComplexityLevel` + `MODEL_MATRIX` 테스트 추가
- [ ] 모든 테스트 `given/when/then` 패턴 준수

---

## 전체 진행률

```
PHASE 1  안전장치 & 상태 영속성    ⬜⬜⬜   0%
PHASE 2  에이전트 클래스 분리      ⬜⬜⬜   0%
PHASE 3  Dynamic Tool Discovery   ⬜⬜⬜   0%
PHASE 4  Model Routing 고도화     ⬜⬜⬜   0%
PHASE 5  HITL                     ⬜⬜⬜   0%
PHASE 6  Observability (LangFuse) ⬜⬜⬜   0%
PHASE 7  병렬 실행                ⬜⬜⬜   0%
PHASE 8  메모리 시스템             ⬜⬜⬜   0%
PHASE 9  REST API & 스트리밍      ⬜⬜⬜   0%
PHASE 10 테스트 보강               🔨⬜⬜  10%

[MVP v0.1] ████████████░░░░░░░░░░░░  핵심 엔진 완료
```

---

## 다음에 시작할 작업

> **권장 순서**: PHASE 1 → PHASE 4 → PHASE 2 → PHASE 3

1. **PHASE 1-1** `src/core/cost_guard.py` 신규 생성
2. **PHASE 1-2** `main.py`에 `SqliteSaver` 체크포인터 연결
3. **PHASE 1-3** `AgentState` v2 필드 추가 및 기존 테스트 통과 확인
4. **PHASE 4-1** `model_router.py`에 `ComplexityLevel` + `MODEL_MATRIX` 추가

---

*마지막 업데이트: 2026-03-18*
