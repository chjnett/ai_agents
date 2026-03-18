import pytest
from unittest.mock import AsyncMock, MagicMock


class TestIntentRouter:
    """Intent Router 단위 테스트 - given/when/then 패턴"""

    @pytest.fixture
    def mock_router(self):
        from src.core.intent_router import IntentRouter, RoutingDecision, IntentType
        router = IntentRouter.__new__(IntentRouter)
        router.chain = AsyncMock()
        return router, IntentType, RoutingDecision

    class TestResearchIntent:
        async def test_how_does_x_work_is_research(self, mock_router):
            # given
            router, IntentType, RoutingDecision = mock_router
            router.chain.ainvoke = AsyncMock(return_value=MagicMock(
                content='{"intent": "research", "confidence": 0.95, "reasoning": "User wants to understand", "recommended_workflow": "research_only", "suggested_agents": ["researcher"]}'
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
            router.chain.ainvoke = AsyncMock(return_value=MagicMock(
                content='{"intent": "implement", "confidence": 0.9, "reasoning": "User wants to build", "recommended_workflow": "plan_execute", "suggested_agents": ["planner", "coder"]}'
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
            router.chain.ainvoke = AsyncMock(return_value=MagicMock(
                content='{"intent": "fix", "confidence": 0.92, "reasoning": "User has a bug", "recommended_workflow": "plan_execute", "suggested_agents": ["coder"]}'
            ))

            # when
            result = await router.classify("I'm getting a TypeError: NoneType is not subscriptable")

            # then
            assert result.intent == IntentType.FIX


class TestModelRouter:
    """Model Router 단위 테스트"""

    class TestCategoryMapping:
        def test_quick_category_returns_haiku(self):
            # given
            from src.core.model_router import ModelRouter, TaskCategory
            router = ModelRouter()

            # when
            model = router.get_model(TaskCategory.QUICK)

            # then
            assert model is not None

        def test_override_changes_model(self):
            # given
            from src.core.model_router import ModelRouter, TaskCategory
            router = ModelRouter(overrides={"quick": "claude-sonnet-4-6"})

            # when
            model_name = router.mapping[TaskCategory.QUICK]

            # then
            assert model_name == "claude-sonnet-4-6"

        def test_intent_to_category_mapping(self):
            # given
            from src.core.model_router import ModelRouter
            router = ModelRouter()

            # when/then
            for intent in ["research", "implement", "fix", "generate"]:
                model = router.get_model_for_intent(intent)
                assert model is not None


class TestLoopLogic:
    """Ralph Loop 로직 단위 테스트"""

    class TestShouldContinueLoop:
        def test_continues_when_tasks_remain(self):
            # given
            from src.core.workflow_engine import should_continue_loop
            state = {
                "loop_iteration": 1,
                "max_loop_iterations": 10,
                "loop_active": True,
                "plan": [
                    {"id": "task-01", "status": "done"},
                    {"id": "task-02", "status": "pending"},
                ],
                "completed_tasks": [{"task_id": "task-01"}],
            }

            # when
            result = should_continue_loop(state)

            # then
            assert result == "executor"

        def test_stops_at_max_iterations(self):
            # given
            from src.core.workflow_engine import should_continue_loop
            state = {
                "loop_iteration": 10,
                "max_loop_iterations": 10,
                "loop_active": True,
                "plan": [{"id": "task-01"}],
                "completed_tasks": [],
            }

            # when
            result = should_continue_loop(state)

            # then
            assert result == "finalizer"

        def test_stops_when_all_tasks_done(self):
            # given
            from src.core.workflow_engine import should_continue_loop
            state = {
                "loop_iteration": 2,
                "max_loop_iterations": 10,
                "loop_active": True,
                "plan": [{"id": "task-01"}, {"id": "task-02"}],
                "completed_tasks": [
                    {"task_id": "task-01"},
                    {"task_id": "task-02"},
                ],
            }

            # when
            result = should_continue_loop(state)

            # then
            assert result == "finalizer"
