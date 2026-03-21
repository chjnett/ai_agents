"""
My Agent System CLI entrypoint.
"""

from __future__ import annotations

import asyncio
import uuid

from dotenv import load_dotenv

load_dotenv()


async def _run_graph_with_resume(graph, initial_state, config):
    """
    Run graph and handle interrupt/resume cycles when present.
    Works with upcoming HITL interrupt() nodes as well.
    """
    from langgraph.types import Command

    result = await graph.ainvoke(initial_state, config=config)

    while isinstance(result, dict) and "__interrupt__" in result:
        interrupts = result.get("__interrupt__", [])
        if interrupts:
            print("\n[Approval Required]")
            for idx, item in enumerate(interrupts, start=1):
                value = getattr(item, "value", item)
                print(f"{idx}. {value}")
        user_input = input("Approve / modify:<instruction> / cancel > ").strip()
        result = await graph.ainvoke(Command(resume=user_input), config=config)

    return result


def _build_graph_with_checkpointer():
    from src.core.workflow_engine import build_orchestration_graph

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ModuleNotFoundError:
        print("[warn] langgraph sqlite checkpointer not available. Running without persistence.")
        return build_orchestration_graph()

    checkpointer = SqliteSaver.from_conn_string("checkpoints.db")
    return build_orchestration_graph(checkpointer=checkpointer)


async def confirm_orchestration(message: str, mode: str) -> tuple[bool, str]:
    from src.core.intent_router import IntentRouter
    from src.core.model_router import ModelRouter, TaskCategory, ComplexityLevel, estimate_complexity, OrchestrationMode

    router = IntentRouter()
    # 1. 의도 분류
    decision = await router.classify(message)
    intent = decision.intent
    category_map = {
        "research": TaskCategory.QUICK,
        "implement": TaskCategory.DEEP,
        "investigate": TaskCategory.ANALYSIS,
        "evaluate": TaskCategory.ULTRABRAIN,
        "fix": TaskCategory.DEEP,
        "generate": TaskCategory.CREATIVE,
    }
    category = category_map.get(intent, TaskCategory.QUICK)
    complexity = estimate_complexity(message)

    model_router = ModelRouter()
    mode_enum = OrchestrationMode(mode)
    assigned_model = model_router.get_orchestrated_model(category, message, mode=mode_enum)

    print("\n" + "=" * 40)
    print("  [Model Orchestration Confirmation]")
    print(f"  > Intent:     {intent}")
    print(f"  > Category:   {category.value}")
    print(f"  > Complexity: {complexity.value}")
    print(f"  > Mode:       {mode}")
    print(f"  > Model:      \033[92m{assigned_model}\033[0m")
    print("=" * 40)

    while True:
        choice = input("\nProceed? [Y/n/change] > ").strip().lower()
        if choice in ("", "y", "yes"):
            return True, assigned_model
        if choice in ("n", "no"):
            return False, assigned_model
        if choice == "change":
            print("\nAvailable models for this category:")
            levels = [ComplexityLevel.LOW, ComplexityLevel.MEDIUM, ComplexityLevel.HIGH]
            matrix = model_router._build_model_matrix()
            models = []
            for i, lvl in enumerate(levels, 1):
                m = matrix.get((category, lvl), "unknown")
                models.append(m)
                print(f"  {i}. {lvl.value:8} -> {m}")

            change_choice = input("Select model number (1-3) > ").strip()
            if change_choice in ("1", "2", "3"):
                new_model = models[int(change_choice)-1]
                print(f"Changed to: {new_model}")
                return True, new_model
            else:
                print("Invalid choice, returning to main prompt.")


async def run_interactive(mode: str = "balanced"):
    from src.core.workflow_engine import make_initial_state

    print("=" * 60)
    print("  My Agent System v0.2")
    print(f"  Phase 1 enabled | Mode: {mode}")
    print("=" * 60)
    print("Commands: 'quit' to exit, 'help' for tips\n")

    graph = _build_graph_with_checkpointer()

    while True:
        try:
            user_input = input("\nYou > ").strip()
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
            print("  - 'session:<id> <message>' 로 같은 세션을 재개할 수 있습니다.")
            print("  - '--mode [economy|balanced|powerful]' 로 실행 모드를 변경하세요.")
            continue

        session_id = str(uuid.uuid4())
        message = user_input
        if user_input.startswith("session:"):
            try:
                prefix, rest = user_input.split(" ", 1)
                session_id = prefix.removeprefix("session:").strip()
                message = rest.strip()
            except ValueError:
                print("형식: session:<세션ID> <메시지>")
                continue

        # Confirmation Step
        ok, finalized_model = await confirm_orchestration(message, mode)
        if not ok:
            print("Execution cancelled.")
            continue

        initial_state = make_initial_state(
            user_request=message,
            session_id=session_id,
            orchestration_mode=mode
        )
        config = {"configurable": {"thread_id": session_id}}

        print("\nThinking...", end="", flush=True)
        try:
            final_state = await _run_graph_with_resume(graph, initial_state, config=config)
            print("\r" + " " * 20 + "\r", end="")

            trace = " -> ".join(final_state.get("workflow_trace", []))
            if trace:
                print(f"\n[{trace}]")

            print(f"Session: {session_id}")
            print(f"Cost: ${final_state.get('total_cost_usd', 0.0):.6f}")
            print(f"Tokens: {final_state.get('total_tokens', 0)}")
            answer = final_state.get("final_answer", "No answer generated.")
            print(f"\nAgent > {answer}\n")
        except Exception as e:
            print(f"\rError: {e}\n")


def main():
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="My Agent System CLI")
    parser.add_argument("--demo", action="store_true", help="Run in demo mode")
    parser.add_argument("--mode", type=str, default="balanced", choices=["economy", "balanced", "powerful"],
                        help="Orchestration mode")

    args = parser.parse_args()

    if args.demo:
        try:
            asyncio.run(run_demo())
        except KeyboardInterrupt:
            print("\nBye!")
    else:
        try:
            asyncio.run(run_interactive(mode=args.mode))
        except KeyboardInterrupt:
            print("\nBye!")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
