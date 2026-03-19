# TESTING_GUIDE.md — 테스트 완전 가이드

> **작성일**: 2026-03-18  
> **환경**: Python 3.14 / macOS / `.venv` 가상환경  
> **현재 테스트 상태**: `6/9 PASS` (mock 방식 불일치 3개 수정 필요 → 이 문서에 수정 방법 포함)

---

## 목차

1. [환경 준비 (첫 시작)](#1-환경-준비-첫-시작)
2. [테스트 파일 구조](#2-테스트-파일-구조)
3. [단위 테스트 실행 (pytest)](#3-단위-테스트-실행-pytest)
4. [실제 API 테스트 (test_manual.py)](#4-실제-api-테스트-test_manualpy)
5. [전체 워크플로우 E2E 테스트](#5-전체-워크플로우-e2e-테스트)
6. [현재 실패하는 테스트 수정 방법](#6-현재-실패하는-테스트-수정-방법)
7. [새 테스트 추가하는 방법](#7-새-테스트-추가하는-방법)
8. [자주 발생하는 오류 & 해결법](#8-자주-발생하는-오류--해결법)

---

## 1. 환경 준비 (첫 시작)

### 1-1. 가상환경 생성 및 패키지 설치

```bash
# 프로젝트 루트로 이동
cd /Users/cheonhyeonjun/workspace/06ai_aiagents/my-agent-system

# 가상환경 생성 (최초 1회)
python3 -m venv .venv

# 핵심 패키지 설치
.venv/bin/pip install \
  langchain langchain-anthropic langchain-openai langchain-google-genai \
  langgraph pydantic python-dotenv \
  pytest pytest-asyncio
```

### 1-2. API 키 확인

`.env` 파일에 실제 API 키가 들어있는지 확인한다.

```bash
# 어떤 키가 유효한지 자동 감지
.venv/bin/python3 -c "
from dotenv import load_dotenv; load_dotenv()
from src.core.intent_router import _select_default_model
print(f'사용 가능한 모델: {_select_default_model()}')
"
```

**예상 출력**:
```
사용 가능한 모델: gpt-4o-mini   ← OPENAI_API_KEY 유효
# 또는
사용 가능한 모델: claude-haiku-4-5  ← ANTHROPIC_API_KEY 유효
```

**`.env` 파일에서 키 형식 확인**:

| 키                  | 올바른 형식                         |
| ------------------- | ----------------------------------- |
| `ANTHROPIC_API_KEY` | `sk-ant-api03-...` 로 시작          |
| `OPENAI_API_KEY`    | `sk-proj-...` 또는 `sk-...` 로 시작 |
| `GOOGLE_API_KEY`    | `AIza...` 로 시작                   |

> ⚠️ **주의**: 키 값 앞뒤에 공백이 있으면 인식 불가. `KEY= value` → `KEY=value` 로 수정.

---

## 2. 테스트 파일 구조

```
my-agent-system/
├── tests/
│   └── test_core.py        # pytest 단위 테스트 (Mock 사용 — API 불필요)
│
└── test_manual.py          # 실제 API 호출 인터랙티브 테스트
```

### 테스트 종류 비교

| 구분                  | 파일                        | API 필요?    | 실행 속도    | 용도             |
| --------------------- | --------------------------- | ------------ | ------------ | ---------------- |
| **단위 테스트**       | `tests/test_core.py`        | ❌ (Mock)     | 빠름 (~1초)  | 로직 검증, CI/CD |
| **인터랙티브 테스트** | `test_manual.py`            | ✅ (실제 LLM) | 보통 (~30초) | 실제 동작 확인   |
| **E2E 워크플로우**    | `test_manual.py --workflow` | ✅ (실제 LLM) | 느림 (~2분)  | 전체 흐름 확인   |

---

## 3. 단위 테스트 실행 (pytest)

### 기본 실행

```bash
cd /Users/cheonhyeonjun/workspace/06ai_aiagents/my-agent-system

# 전체 테스트 실행
.venv/bin/python3 -m pytest tests/test_core.py -v
```

### 특정 클래스/함수만 실행

```bash
# TestLoopLogic 클래스 전체
.venv/bin/python3 -m pytest tests/test_core.py::TestLoopLogic -v

# TestModelRouter 클래스만
.venv/bin/python3 -m pytest tests/test_core.py::TestModelRouter -v

# 특정 함수 하나만
.venv/bin/python3 -m pytest "tests/test_core.py::TestLoopLogic::TestShouldContinueLoop::test_stops_at_max_iterations" -v

# 테스트 이름에 키워드가 포함된 것만
.venv/bin/python3 -m pytest tests/test_core.py -k "loop" -v
```

### 현재 테스트 결과 (2026-03-18 기준)

```
tests/test_core.py::TestIntentRouter::TestResearchIntent::test_how_does_x_work_is_research  FAILED
tests/test_core.py::TestIntentRouter::TestImplementIntent::test_create_x_is_implement       FAILED
tests/test_core.py::TestIntentRouter::TestFixIntent::test_error_message_is_fix              FAILED
tests/test_core.py::TestModelRouter::TestCategoryMapping::test_quick_category_returns_haiku PASSED
tests/test_core.py::TestModelRouter::TestCategoryMapping::test_override_changes_model       FAILED
tests/test_core.py::TestModelRouter::TestCategoryMapping::test_intent_to_category_mapping   PASSED
tests/test_core.py::TestLoopLogic::TestShouldContinueLoop::test_continues_when_tasks_remain PASSED
tests/test_core.py::TestLoopLogic::TestShouldContinueLoop::test_stops_at_max_iterations     PASSED
tests/test_core.py::TestLoopLogic::TestShouldContinueLoop::test_stops_when_all_tasks_done   PASSED
```

> ❌ 실패 원인: `IntentRouter`가 `with_structured_output()` 방식으로 바뀌면서 기존 mock 패턴이 맞지 않음.  
> → [6. 현재 실패하는 테스트 수정 방법](#6-현재-실패하는-테스트-수정-방법) 참고

### pytest 자주 쓰는 옵션

```bash
# 실패한 테스트만 재실행
.venv/bin/python3 -m pytest tests/ --lf

# 처음 실패에서 멈춤
.venv/bin/python3 -m pytest tests/ -x

# 출력 자세히 (print 문 보기)
.venv/bin/python3 -m pytest tests/ -s

# 진행률 표시 없이 간결하게
.venv/bin/python3 -m pytest tests/ -q
```

---

## 4. 실제 API 테스트 (test_manual.py)

실제 LLM API를 호출해서 **눈으로 결과를 확인**하는 테스트.  
pytest와 달리 assert 실패해도 계속 실행해서 전체 케이스를 한번에 확인할 수 있다.

### 기본 실행

```bash
cd /Users/cheonhyeonjun/workspace/06ai_aiagents/my-agent-system
.venv/bin/python3 test_manual.py
```

### 예상 출력

```
=======================================================
  TEST 1: IntentRouter — 의도 분류기
=======================================================

  요청: LangGraph가 어떻게 작동하는지 설명해줘
  →  intent=IntentType.RESEARCH  confidence=0.90  workflow=research_only
  →  이유: 사용자가 LangGraph의 작동 방식에 대한 설명을 요청하고 있다.
  ✅ PASS — 예상: research / research_only

  요청: FastAPI 서버를 새로 만들어줘
  →  intent=IntentType.IMPLEMENT  confidence=0.90  workflow=plan_execute
  ✅ PASS — 예상: implement / plan_execute

  [... 5개 더 ...]

  결과: 7 passed / 0 failed / 7 total

=======================================================
  TEST 2: chat_history — 대화 문맥 반영
=======================================================

  이전 대화: FastAPI 서버 작업 중
  후속 요청: 500 에러가 나
  →  intent=IntentType.FIX  confidence=0.90
  ✅ PASS — 문맥에서 오류 수정 의도를 파악함

=======================================================
  TEST 3: Confidence Guardrail — 모호한 요청 처리
=======================================================

  모호한 요청: 그냥 좀 도와줘
  →  intent=IntentType.UNCLEAR  workflow=ask_clarification
  ✅ PASS

  결과: 3/3 passed

=======================================================
  최종 결과: 3/3 테스트 통과
=======================================================
```

### 테스트 케이스 상세

**TEST 1** — 의도 분류 정확도 (7개 케이스)

| 요청                                   | 예상 intent | 예상 workflow       |
| -------------------------------------- | ----------- | ------------------- |
| "LangGraph 어떻게 작동해?"             | `research`  | `research_only`     |
| "FastAPI 서버 새로 만들어줘"           | `implement` | `plan_execute`      |
| "500 에러 고쳐줘"                      | `fix`       | `plan_execute`      |
| "이 코드 리뷰해주고 의견 줘"           | `evaluate`  | `direct`            |
| "마케팅 블로그 글 작성해줘"            | `generate`  | `direct`            |
| "그냥 좀 도와줘"                       | `unclear`   | `ask_clarification` |
| "리서치도 하고 트레이딩 봇도 만들어줘" | `unclear`   | `ask_clarification` |

**TEST 2** — 대화 이력 문맥 반영  
이전에 FastAPI 서버 작업 중이었다는 context를 주고, "500 에러가 나"라는 짧은 후속 요청이 `fix`로 분류되는지 확인.

**TEST 3** — Confidence Guardrail  
매우 모호한 요청 3개가 모두 `ask_clarification`으로 분류되는지 확인.

---

## 5. 전체 워크플로우 E2E 테스트

### 실행

```bash
.venv/bin/python3 test_manual.py --workflow
```

**추가 실행 항목**:

**TEST 4** — LangGraph 전체 파이프라인 E2E  
`build_orchestration_graph()`를 실제로 실행해서 `intent_gate → executor → finalizer` 전체 흐름이 작동하는지 확인.

예상 출력:
```
=======================================================
  TEST 4: 전체 워크플로우 E2E
=======================================================

  요청: LangGraph의 StateGraph가 뭔지 한 줄로 설명해줘
  실행 중...

  →  workflow trace: intent_gate → executor → finalizer
  →  intent: research

  최종 답변:
  StateGraph는 LangGraph에서 노드(함수)와 엣지(조건부 전환)로 ...

  ✅ PASS — 최종 답변 생성됨
```

> ⏱️ E2E 테스트는 LLM 응답 시간 포함 **1~3분** 소요됨.

### main.py 대화형 CLI로 직접 테스트

```bash
.venv/bin/python3 main.py
```

대화 예시:
```
You > LangGraph가 뭔지 설명해줘
[intent_gate → executor]

Agent > LangGraph는 LLM 여러 개를...

You > FastAPI REST API 만들어줘
[intent_gate → planner → executor(researcher) → executor(coder) → reviewer → finalizer]

Agent > 아키텍처 계획:
  task-01: 요구사항 분석 (researcher)
  task-02: FastAPI 코드 구현 (coder)
  ...

You > quit
```

`[...]` 부분이 **어떤 에이전트를 거쳤는지 trace**를 보여줌.

---

## 6. 현재 실패하는 테스트 수정 방법

### 실패 원인

`IntentRouter`가 `with_structured_output()` 방식으로 변경되면서  
`chain.ainvoke()`가 `MagicMock(content="...")` 대신 **`RoutingDecision` 객체를 직접 반환**하게 됨.  
기존 mock은 문자열 반환을 가정해서 실패.

### 수정 방법

`tests/test_core.py` 파일의 `TestIntentRouter` 섹션 전체를 아래로 교체.

#### 수정된 `TestIntentRouter` (복붙하면 됨)

```python
class TestIntentRouter:
    """Intent Router 단위 테스트 — given/when/then 패턴"""

    @pytest.fixture
    def mock_router(self):
        """
        with_structured_output 방식에 맞는 mock.
        chain.ainvoke가 RoutingDecision 객체를 직접 반환하도록 설정.
        """
        from src.core.intent_router import IntentRouter, RoutingDecision, IntentType

        router = IntentRouter.__new__(IntentRouter)
        router.chain = AsyncMock()
        return router, IntentType, RoutingDecision

    class TestResearchIntent:
        async def test_how_does_x_work_is_research(self, mock_router):
            # given
            router, IntentType, RoutingDecision = mock_router
            router.chain.ainvoke = AsyncMock(return_value=RoutingDecision(
                intent=IntentType.RESEARCH,
                confidence=0.95,
                reasoning="User wants to understand",
                recommended_workflow="research_only",
                suggested_agents=["researcher"],
            ))
            # when
            result = await router.classify("how does Redis work?")
            # then
            assert result.intent == IntentType.RESEARCH
            assert result.confidence >= 0.8
            assert result.recommended_workflow == "research_only"

    class TestImplementIntent:
        async def test_create_x_is_implement(self, mock_router):
            # given
            router, IntentType, RoutingDecision = mock_router
            router.chain.ainvoke = AsyncMock(return_value=RoutingDecision(
                intent=IntentType.IMPLEMENT,
                confidence=0.9,
                reasoning="User wants to build",
                recommended_workflow="plan_execute",
                suggested_agents=["planner", "coder"],
            ))
            # when
            result = await router.classify("create a REST API for authentication")
            # then
            assert result.intent == IntentType.IMPLEMENT
            assert result.recommended_workflow == "plan_execute"
            assert "coder" in result.suggested_agents

    class TestFixIntent:
        async def test_error_message_is_fix(self, mock_router):
            # given
            router, IntentType, RoutingDecision = mock_router
            router.chain.ainvoke = AsyncMock(return_value=RoutingDecision(
                intent=IntentType.FIX,
                confidence=0.92,
                reasoning="User has a bug",
                recommended_workflow="plan_execute",
                suggested_agents=["coder"],
            ))
            # when
            result = await router.classify("I'm getting a TypeError: NoneType is not subscriptable")
            # then
            assert result.intent == IntentType.FIX

    class TestUnclearIntent:
        async def test_vague_request_becomes_unclear(self, mock_router):
            # given — confidence가 0.65 미만이면 Guardrail이 UNCLEAR로 전환
            router, IntentType, RoutingDecision = mock_router
            router.chain.ainvoke = AsyncMock(return_value=RoutingDecision(
                intent=IntentType.RESEARCH,
                confidence=0.4,            # ← 0.65 미만 → Guardrail 발동
                reasoning="Too vague",
                recommended_workflow="research_only",
                suggested_agents=[],
            ))
            # when
            result = await router.classify("그냥 좀 도와줘")
            # then — Confidence Guardrail이 UNCLEAR로 바꿔야 함
            assert result.intent == IntentType.UNCLEAR
            assert result.recommended_workflow == "ask_clarification"
```

#### `TestModelRouter` — `test_override_changes_model` 수정

```python
def test_override_changes_model(self):
    # given
    from src.core.model_router import ModelRouter, TaskCategory
    # 수정: "quick" 대신 TaskCategory.QUICK 사용 (Enum 키 방식)
    router = ModelRouter(overrides={"quick": "claude-sonnet-4-6"})
    # when
    model_name = router.mapping.get(TaskCategory.QUICK)
    # then
    assert model_name == "claude-sonnet-4-6"
```

---

## 7. 새 테스트 추가하는 방법

### given/when/then 패턴 (필수)

```python
async def test_새로운_케이스(self, mock_router):
    # given: 테스트 조건 설정
    router, IntentType, RoutingDecision = mock_router
    router.chain.ainvoke = AsyncMock(return_value=RoutingDecision(
        intent=IntentType.GENERATE,
        confidence=0.88,
        reasoning="User wants content created",
        recommended_workflow="direct",
        suggested_agents=["writer"],
    ))

    # when: 실행
    result = await router.classify("블로그 글 써줘")

    # then: 검증
    assert result.intent == IntentType.GENERATE
    assert result.recommended_workflow == "direct"
```

### 새 Mock 빠르게 만드는 템플릿

```python
# IntentRouter Mock 기본 템플릿
router.chain.ainvoke = AsyncMock(return_value=RoutingDecision(
    intent=IntentType.????,          # 테스트할 의도
    confidence=0.9,                  # 확신도 (0.65 이상이면 Guardrail 미발동)
    reasoning="reason here",
    recommended_workflow="????",     # plan_execute | direct | research_only | ask_clarification
    suggested_agents=["????"],
))
```

### Loop 로직 테스트 기본 상태 구조

```python
state = {
    "loop_iteration":      1,   # 현재 반복 횟수
    "max_loop_iterations": 10,  # 최대 반복 한도
    "loop_active":         True,
    "plan": [
        {"id": "task-01", "status": "done"},
        {"id": "task-02", "status": "pending"},  # 미완료 태스크
    ],
    "completed_tasks": [
        {"task_id": "task-01"},  # 완료된 태스크
    ],
}
```

---

## 8. 자주 발생하는 오류 & 해결법

### 오류 1: `ModuleNotFoundError: No module named 'langchain_anthropic'`

```bash
# 패키지 설치 안 됨
.venv/bin/pip install langchain-anthropic langchain-openai langgraph
```

---

### 오류 2: `AuthenticationError: invalid x-api-key`

```bash
# 키 확인
.venv/bin/python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os
key = os.getenv('OPENAI_API_KEY', '')
print(f'길이: {len(key)}, 시작: {key[:8]}...')
"
```

**원인**: `.env` 파일에 실제 키가 아닌 `your_api_key_here` 플레이스홀더가 있거나, 키 값 앞에 공백이 있음.

**해결**: `.env` 파일에서 직접 수정
```
OPENAI_API_KEY=sk-proj-실제키값  ← 앞뒤 공백 없이
```

---

### 오류 3: `UserWarning: Core Pydantic V1 functionality isn't compatible with Python 3.14`

```
UserWarning: Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.
```

**무시해도 됨** — Python 3.14와 일부 LangChain 내부 의존성 간 경고.  
실제 동작에는 영향 없음. 향후 LangChain 업데이트로 해결 예정.

---

### 오류 4: pytest `FAILED` — AssertionError

```bash
# 상세 에러 메시지 보기
.venv/bin/python3 -m pytest tests/test_core.py -v -s

# 특정 테스트만 디버깅
.venv/bin/python3 -m pytest "tests/test_core.py::TestLoopLogic" -v -s
```

---

### 오류 5: `asyncio: mode=Mode.AUTO` 관련 경고

`pyproject.toml`에 이미 설정되어 있어서 정상:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

### 전체 테스트 빠른 재실행 스크립트

```bash
# 단위 테스트 (빠름, API 불필요)
.venv/bin/python3 -m pytest tests/ -v --tb=short

# API 인터랙티브 테스트 (실제 LLM 호출)
.venv/bin/python3 test_manual.py

# 전체 E2E 포함
.venv/bin/python3 test_manual.py --workflow
```

---

*마지막 업데이트: 2026-03-18*
