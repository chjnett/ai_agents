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


async def run_interactive():
    from src.core.workflow_engine import make_initial_state

    print("=" * 60)
    print("  My Agent System v0.2")
    print("  Phase 1 enabled: CostGuard + Checkpointer")
    print("=" * 60)
    print("Commands: 'quit' to exit, 'help' for tips\n")

    graph = _build_graph_with_checkpointer()

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
            print("  - 'session:<id> <message>' 로 같은 세션을 재개할 수 있습니다.")
            print("  - Ask 'how does X work' -> research mode")
            print("  - Ask 'implement X' -> plan + execute mode")
            print("  - Ask 'fix my code: <code>' -> fix mode\n")
            continue

        session_id = str(uuid.uuid4())
        message = user_input
        if user_input.startswith("session:"):
            # format: session:<uuid> message...
            try:
                prefix, rest = user_input.split(" ", 1)
                session_id = prefix.removeprefix("session:").strip()
                message = rest.strip()
            except ValueError:
                print("형식: session:<세션ID> <메시지>")
                continue

        initial_state = make_initial_state(user_request=message, session_id=session_id)
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
        except asyncio.CancelledError:
            print("\rCancelled.\n")
        except KeyboardInterrupt:
            print("\rCancelled.\n")
        except Exception as e:
            print(f"\rError: {e}\n")


async def run_demo():
    from src.core.workflow_engine import make_initial_state

    demo_requests = [
        "How does the LangGraph StateGraph work?",
        "What is the difference between RAG and fine-tuning?",
    ]
    graph = _build_graph_with_checkpointer()
    print("=== Demo Mode ===\n")

    for request in demo_requests:
        session_id = str(uuid.uuid4())
        initial_state = make_initial_state(
            user_request=request,
            session_id=session_id,
            max_loop_iterations=5,
        )
        config = {"configurable": {"thread_id": session_id}}
        final_state = await _run_graph_with_resume(graph, initial_state, config=config)

        trace = " -> ".join(final_state.get("workflow_trace", []))
        print(f"Request: {request}")
        print(f"Session: {session_id}")
        print(f"Workflow: {trace}")
        print(f"Intent:   {final_state.get('intent', 'unknown')}")
        print(f"Cost:     ${final_state.get('total_cost_usd', 0.0):.6f}")
        print(f"Tokens:   {final_state.get('total_tokens', 0)}")
        print(f"\nAnswer:\n{final_state.get('final_answer', 'No answer')}\n")
        print("=" * 60 + "\n")


def main():
    import sys

    if "--demo" in sys.argv:
        try:
            asyncio.run(run_demo())
        except KeyboardInterrupt:
            print("\nBye!")
    else:
        try:
            asyncio.run(run_interactive())
        except KeyboardInterrupt:
            print("\nBye!")


if __name__ == "__main__":
    main()
