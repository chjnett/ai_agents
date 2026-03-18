"""
My Agent System - MVP 엔트리포인트

oh-my-openagent의 핵심 아키텍처를 Python + LangGraph로 구현한 멀티-에이전트 시스템.

실행 방법:
    python main.py            # 대화형 CLI
    python main.py --demo     # 데모 실행

필수 환경 변수 (.env 파일에 설정):
    ANTHROPIC_API_KEY
    OPENAI_API_KEY (선택)
    GOOGLE_API_KEY (선택)
"""

import asyncio
import uuid
from dotenv import load_dotenv

load_dotenv()


async def run_interactive():
    """대화형 CLI 모드"""
    from src.core.workflow_engine import build_orchestration_graph

    print("=" * 60)
    print("  My Agent System v0.1")
    print("  Inspired by oh-my-openagent architecture")
    print("=" * 60)
    print("Commands: 'quit' to exit, 'help' for tips\n")

    graph = build_orchestration_graph()

    while True:
        try:
            user_input = input("You > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break
        if user_input.lower() == "help":
            print("\nTips:")
            print("  - Ask 'how does X work' → research mode")
            print("  - Ask 'implement X' → plan + execute mode")
            print("  - Ask 'fix my code: <code>' → fix mode")
            print("  - Ask 'write a report about X' → generate mode\n")
            continue

        session_id = str(uuid.uuid4())

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

        print("\nThinking...", end="", flush=True)

        try:
            final_state = await graph.ainvoke(initial_state)

            print("\r" + " " * 20 + "\r", end="")  # "Thinking..." 지움

            # 워크플로우 트레이스 출력 (어떤 에이전트를 썼는지)
            trace = " → ".join(final_state.get("workflow_trace", []))
            if trace:
                print(f"\n[{trace}]\n")

            answer = final_state.get("final_answer", "No answer generated.")
            print(f"Agent > {answer}\n")

        except Exception as e:
            print(f"\rError: {e}\n")


async def run_demo():
    """데모 모드: 미리 정의된 질문들로 시스템 테스트"""
    from src.core.workflow_engine import build_orchestration_graph

    demo_requests = [
        "How does the LangGraph StateGraph work?",
        "What is the difference between RAG and fine-tuning?",
    ]

    graph = build_orchestration_graph()

    print("=== Demo Mode ===\n")

    for request in demo_requests:
        print(f"Request: {request}")
        print("-" * 40)

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

        final_state = await graph.ainvoke(initial_state)

        trace = " → ".join(final_state.get("workflow_trace", []))
        print(f"Workflow: {trace}")
        print(f"Intent:   {final_state.get('intent', 'unknown')}")
        print(f"\nAnswer:\n{final_state.get('final_answer', 'No answer')}\n")
        print("=" * 60 + "\n")


def main():
    import sys
    if "--demo" in sys.argv:
        asyncio.run(run_demo())
    else:
        asyncio.run(run_interactive())


if __name__ == "__main__":
    main()
