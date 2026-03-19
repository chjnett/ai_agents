#!/usr/bin/env python3
"""
test_manual.py — 수동 인터랙티브 테스트

실제 API를 호출해서 IntentRouter와 워크플로우 엔진을 직접 테스트한다.
pytest가 아닌 눈으로 결과를 확인하는 용도.

실행:
    .venv/bin/python test_manual.py
    .venv/bin/python test_manual.py --workflow   # 전체 LangGraph 워크플로우까지
"""

import asyncio
import sys
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
# ANSI 컬러 출력 헬퍼
# ──────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):    print(f"  {GREEN}✅ {msg}{RESET}")
def warn(msg):  print(f"  {YELLOW}⚠️  {msg}{RESET}")
def fail(msg):  print(f"  {RED}❌ {msg}{RESET}")
def info(msg):  print(f"  {CYAN}→  {msg}{RESET}")
def header(msg): print(f"\n{BOLD}{'='*55}\n  {msg}\n{'='*55}{RESET}")


# ──────────────────────────────────────────────
# 1. IntentRouter 단독 테스트
# ──────────────────────────────────────────────

TEST_CASES = [
    # (요청 문자열, 예상 intent, 예상 workflow)
    ("LangGraph가 어떻게 작동하는지 설명해줘",         "research",    "research_only"),
    ("FastAPI 서버를 새로 만들어줘",                  "implement",   "plan_execute"),
    ("500 에러가 계속 발생해. 고쳐줘",                 "fix",         "plan_execute"),
    ("이 코드 리뷰해주고 의견 줘",                     "evaluate",    "direct"),
    ("마케팅 블로그 글 작성해줘",                      "generate",    "direct"),
    ("그냥 좀 도와줘",                                "unclear",     "ask_clarification"),
    ("리서치도 하고 동시에 트레이딩 봇도 만들어줘",    "unclear",     "ask_clarification"),
]

async def test_intent_router():
    header("TEST 1: IntentRouter — 의도 분류기")
    from src.core.intent_router import IntentRouter

    router = IntentRouter()
    passed = failed = 0

    for request, expected_intent, expected_workflow in TEST_CASES:
        print(f"\n  {BOLD}요청:{RESET} {request}")
        try:
            result = await router.classify(request)
            intent_ok    = result.intent == expected_intent
            workflow_ok  = result.recommended_workflow == expected_workflow

            info(f"intent={result.intent}  confidence={result.confidence:.2f}  workflow={result.recommended_workflow}")
            info(f"이유: {result.reasoning}")

            if intent_ok and workflow_ok:
                ok(f"PASS — 예상: {expected_intent} / {expected_workflow}")
                passed += 1
            else:
                warn(f"MISMATCH — 예상: {expected_intent}/{expected_workflow}  실제: {result.intent}/{result.recommended_workflow}")
                failed += 1

        except Exception as e:
            fail(f"ERROR: {e}")
            failed += 1

    print(f"\n  결과: {GREEN}{passed} passed{RESET} / {RED}{failed} failed{RESET} / {passed+failed} total")
    return failed == 0


# ──────────────────────────────────────────────
# 2. chat_history 문맥 테스트
# ──────────────────────────────────────────────

async def test_intent_with_history():
    header("TEST 2: chat_history — 대화 문맥 반영")
    from src.core.intent_router import IntentRouter
    from langchain_core.messages import HumanMessage, AIMessage

    router = IntentRouter()

    # 이전 대화: FastAPI 서버 작업 중이었음
    history = [
        HumanMessage(content="FastAPI 서버 기본 구조 만들어줘"),
        AIMessage(content="FastAPI 서버 구조를 생성했습니다. /health 엔드포인트를 추가했어요."),
    ]

    followup = "500 에러가 나"   # 문맥 없이는 모호하지만 이전 대화로 fix임을 알 수 있어야 함

    print(f"\n  {BOLD}이전 대화:{RESET} FastAPI 서버 작업 중")
    print(f"  {BOLD}후속 요청:{RESET} {followup}")

    result = await router.classify(followup, chat_history=history)
    info(f"intent={result.intent}  confidence={result.confidence:.2f}  workflow={result.recommended_workflow}")
    info(f"이유: {result.reasoning}")

    if result.intent in ("fix", "investigate"):
        ok("PASS — 문맥에서 오류 수정 의도를 파악함")
        return True
    else:
        warn(f"MISMATCH — 예상: fix 또는 investigate  실제: {result.intent}")
        return False


# ──────────────────────────────────────────────
# 3. Confidence Guardrail 테스트
# ──────────────────────────────────────────────

async def test_confidence_guardrail():
    header("TEST 3: Confidence Guardrail — 모호한 요청 처리")
    from src.core.intent_router import IntentRouter, IntentType

    router = IntentRouter()
    vague_requests = [
        "그냥 좀 도와줘",
        "뭔가 만들어줘",
        "어 그거",
    ]

    passed = 0
    for req in vague_requests:
        print(f"\n  {BOLD}모호한 요청:{RESET} {req}")
        result = await router.classify(req)
        info(f"intent={result.intent}  confidence={result.confidence:.2f}  workflow={result.recommended_workflow}")

        if result.recommended_workflow == "ask_clarification":
            ok("PASS — ask_clarification으로 올바르게 분류")
            passed += 1
        else:
            warn(f"MISMATCH — 예상: ask_clarification  실제: {result.recommended_workflow}")

    print(f"\n  결과: {passed}/{len(vague_requests)} passed")
    return passed == len(vague_requests)


# ──────────────────────────────────────────────
# 4. 전체 워크플로우 E2E 테스트 (--workflow 옵션)
# ──────────────────────────────────────────────

async def test_workflow_e2e():
    header("TEST 4: 전체 워크플로우 E2E")
    from src.core.workflow_engine import build_orchestration_graph
    import uuid

    graph = build_orchestration_graph()

    # research_only 워크플로우 (가장 빠름)
    request = "LangGraph의 StateGraph가 뭔지 한 줄로 설명해줘"
    print(f"\n  {BOLD}요청:{RESET} {request}")

    initial_state = {
        "messages": [],
        "user_request": request,
        "session_id": str(uuid.uuid4()),
        "intent": "",
        "recommended_workflow": "direct",
        "plan": None,
        "acceptance_criteria": [],
        "current_task_index": 0,
        "completed_tasks": [],
        "failed_tasks": [],
        "loop_active": True,
        "loop_iteration": 0,
        "max_loop_iterations": 5,
        "retry_count": 0,
        "consecutive_failures": 0,
        "final_answer": None,
        "workflow_trace": [],
    }

    print("  실행 중...", end="", flush=True)
    final_state = await graph.ainvoke(initial_state)
    print("\r" + " " * 20 + "\r", end="")

    trace = " → ".join(final_state.get("workflow_trace", []))
    answer = final_state.get("final_answer", "No answer")

    info(f"workflow trace: {trace}")
    info(f"intent: {final_state.get('intent')}")
    print(f"\n  {BOLD}최종 답변:{RESET}")
    print(f"  {answer[:300]}{'...' if len(answer) > 300 else ''}")

    if final_state.get("final_answer"):
        ok("PASS — 최종 답변 생성됨")
        return True
    else:
        fail("FAIL — final_answer 없음")
        return False


# ──────────────────────────────────────────────
# 메인 실행
# ──────────────────────────────────────────────

async def main():
    run_workflow = "--workflow" in sys.argv

    results = []

    # 기본 테스트 (API 호출 최소화)
    results.append(await test_intent_router())
    results.append(await test_intent_with_history())
    results.append(await test_confidence_guardrail())

    # 전체 워크플로우 (옵션)
    if run_workflow:
        results.append(await test_workflow_e2e())

    # 총 결과
    passed = sum(results)
    total = len(results)
    print(f"\n{BOLD}{'='*55}")
    print(f"  최종 결과: {passed}/{total} 테스트 통과")
    print(f"{'='*55}{RESET}")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
