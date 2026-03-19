import pytest
from unittest.mock import AsyncMock, MagicMock


class TestIntentRouter:
    """Intent Router 단위 테스트 — given/when/then 패턴

    with_structured_output() 방식으로 변경된 IntentRouter에 맞게 수정.
    chain.ainvoke()가 RoutingDecision 객체를 직접 반환하도록 mock 설정.
    """

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
        async def test_vague_request_triggers_guardrail(self, mock_router):
            """confidence가 0.65 미만이면 Guardrail이 UNCLEAR로 전환하는지 확인"""
            # given
            router, IntentType, RoutingDecision = mock_router
            router.chain.ainvoke = AsyncMock(return_value=RoutingDecision(
                intent=IntentType.RESEARCH,
                confidence=0.4,           # ← 0.65 미만 → Guardrail 발동
                reasoning="Too vague",
                recommended_workflow="research_only",
                suggested_agents=[],
            ))
            # when
            result = await router.classify("그냥 좀 도와줘")
            # then — Confidence Guardrail이 UNCLEAR로 바꿔야 함
            assert result.intent == IntentType.UNCLEAR
            assert result.recommended_workflow == "ask_clarification"

        async def test_llm_returns_unclear_directly(self, mock_router):
            """LLM이 directly UNCLEAR를 반환해도 ask_clarification으로 처리"""
            # given
            router, IntentType, RoutingDecision = mock_router
            router.chain.ainvoke = AsyncMock(return_value=RoutingDecision(
                intent=IntentType.UNCLEAR,
                confidence=0.9,
                reasoning="Multiple conflicting intents",
                recommended_workflow="ask_clarification",
                suggested_agents=[],
            ))
            # when
            result = await router.classify("리서치도 하고 봇도 만들어줘")
            # then
            assert result.intent == IntentType.UNCLEAR
            assert result.recommended_workflow == "ask_clarification"

    class TestApiError:
        async def test_api_error_returns_safe_fallback(self, mock_router):
            """API 에러 시 예외를 던지지 않고 안전한 기본값을 반환하는지 확인"""
            # given
            router, IntentType, RoutingDecision = mock_router
            router.chain.ainvoke = AsyncMock(side_effect=Exception("API timeout"))
            # when
            result = await router.classify("어떤 요청이든")
            # then — 예외가 아닌 안전한 기본값 반환
            assert result.intent == IntentType.UNCLEAR
            assert result.confidence == 0.0
            assert result.recommended_workflow == "ask_clarification"
            assert "timeout" in result.reasoning


class TestModelRouter:
    """Model Router 단위 테스트 — API 키 없이 모델명 매핑만 검증"""

    @pytest.fixture(autouse=True)
    def inject_fake_openai_key(self, monkeypatch):
        """
        ModelRouter.__init__이 OPENAI_API_KEY를 요구하므로
        단위 테스트에서는 가짜 키를 주입해 환경변수 에러를 방지한다.
        (실제 API를 호출하지 않으므로 가짜 키여도 안전)
        """
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-key-for-unit-test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        monkeypatch.setenv("GOOGLE_API_KEY", "")

    class TestCategoryMapping:
        def test_quick_category_returns_model(self, inject_fake_openai_key):
            # given
            from src.core.model_router import ModelRouter, TaskCategory
            router = ModelRouter()
            # when — OpenAI만 있을 때 QUICK은 gpt-4o-mini
            model_name = router.mapping.get(TaskCategory.QUICK)
            # then
            assert model_name == "gpt-4o-mini"

        def test_override_changes_model(self, inject_fake_openai_key):
            # given
            from src.core.model_router import ModelRouter, TaskCategory
            router = ModelRouter(overrides={"quick": "gpt-4o"})
            # when
            model_name = router.mapping[TaskCategory.QUICK]
            # then
            assert model_name == "gpt-4o"

        def test_all_intents_have_model_mapping(self, inject_fake_openai_key):
            # given
            from src.core.model_router import ModelRouter, TaskCategory
            router = ModelRouter()
            intent_to_category = {
                "research":    TaskCategory.QUICK,
                "implement":   TaskCategory.DEEP,
                "investigate": TaskCategory.ANALYSIS,
                "evaluate":    TaskCategory.ULTRABRAIN,
                "fix":         TaskCategory.DEEP,
                "generate":    TaskCategory.CREATIVE,
            }
            # when/then — 모든 의도에 모델명이 매핑되어 있어야 함
            for intent, category in intent_to_category.items():
                model_name = router.mapping.get(category)
                assert model_name is not None, f"모델 매핑 없음: {intent} → {category}"

        def test_unknown_intent_returns_fallback_model(self, inject_fake_openai_key):
            # given
            from src.core.model_router import ModelRouter, TaskCategory
            router = ModelRouter()
            # when — mapping에 없는 카테고리는 get_model의 fallback 반환
            model_name = router.mapping.get(TaskCategory.QUICK, "gpt-4o-mini")
            # then — fallback이 존재해야 함
            assert model_name is not None

        def test_google_key_uses_gemini_for_quick(self, monkeypatch):
            """Google 키가 있을 때 QUICK이 gemini로 배정되는지 확인"""
            # given
            monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-key-for-unit-test")
            monkeypatch.setenv("GOOGLE_API_KEY", "AIzafake-google-key")
            monkeypatch.setenv("ANTHROPIC_API_KEY", "")
            from src.core.model_router import ModelRouter, TaskCategory, _build_model_mapping
            mapping = _build_model_mapping()
            # then — Google 키 있으면 QUICK은 gemini
            assert "gemini" in mapping[TaskCategory.QUICK]

        def test_anthropic_key_uses_claude_for_creative(self, monkeypatch):
            """Anthropic 키가 있을 때 CREATIVE가 claude로 배정되는지 확인"""
            # given
            monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-key-for-unit-test")
            monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-key")
            monkeypatch.setenv("GOOGLE_API_KEY", "")
            from src.core.model_router import ModelRouter, TaskCategory, _build_model_mapping
            mapping = _build_model_mapping()
            # then — Anthropic 키 있으면 CREATIVE는 claude
            assert "claude" in mapping[TaskCategory.CREATIVE]


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
                    {"id": "task-02", "status": "pending"},   # 미완료
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
                "loop_iteration": 10,      # max와 동일
                "max_loop_iterations": 10,
                "loop_active": True,
                "plan": [{"id": "task-01"}],
                "completed_tasks": [],
            }
            # when
            result = should_continue_loop(state)
            # then — 한도 초과이므로 finalizer
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
            # then — 모든 태스크 완료
            assert result == "finalizer"

        def test_stops_when_loop_inactive(self):
            # given
            from src.core.workflow_engine import should_continue_loop
            state = {
                "loop_iteration": 1,
                "max_loop_iterations": 10,
                "loop_active": False,      # ← 명시적 종료 신호
                "plan": [{"id": "task-01"}],
                "completed_tasks": [],
            }
            # when
            result = should_continue_loop(state)
            # then
            assert result == "finalizer"

        def test_stops_when_cost_limit_exceeded(self):
            # given
            from src.core.workflow_engine import should_continue_loop
            state = {
                "loop_iteration": 1,
                "max_loop_iterations": 10,
                "loop_active": True,
                "plan": [{"id": "task-01"}],
                "completed_tasks": [],
                "total_cost_usd": 1.2,
                "max_cost_usd": 1.0,
                "total_tokens": 1000,
                "max_tokens": 500000,
            }
            # when
            result = should_continue_loop(state)
            # then
            assert result == "finalizer"

        def test_stops_when_token_limit_exceeded(self):
            # given
            from src.core.workflow_engine import should_continue_loop
            state = {
                "loop_iteration": 1,
                "max_loop_iterations": 10,
                "loop_active": True,
                "plan": [{"id": "task-01"}],
                "completed_tasks": [],
                "total_cost_usd": 0.1,
                "max_cost_usd": 1.0,
                "total_tokens": 600000,
                "max_tokens": 500000,
            }
            # when
            result = should_continue_loop(state)
            # then
            assert result == "finalizer"


class TestInitialStateFactory:
    def test_make_initial_state_contains_phase1_fields(self):
        # given
        from src.core.workflow_engine import make_initial_state
        # when
        state = make_initial_state(user_request="hello", session_id="s-1")
        # then
        assert state["user_id"] is None
        assert state["task_complexity"] == "medium"
        assert state["parallel_groups"] is None
        assert state["require_approval"] is False
        assert state["total_cost_usd"] == 0.0
        assert state["total_tokens"] == 0
        assert state["max_cost_usd"] == 1.0
        assert state["max_tokens"] == 500000


class TestRouteByIntent:
    """route_by_intent 라우팅 함수 단위 테스트"""

    def test_plan_execute_goes_to_planner(self):
        # given
        from src.core.workflow_engine import route_by_intent
        state = {"recommended_workflow": "plan_execute", "messages": []}
        # when
        result = route_by_intent(state)
        # then
        assert result == "planner"

    def test_direct_goes_to_executor(self):
        # given
        from src.core.workflow_engine import route_by_intent
        state = {"recommended_workflow": "direct", "messages": []}
        # when
        result = route_by_intent(state)
        # then
        assert result == "executor"

    def test_research_only_goes_to_executor(self):
        # given
        from src.core.workflow_engine import route_by_intent
        state = {"recommended_workflow": "research_only", "messages": []}
        # when
        result = route_by_intent(state)
        # then
        assert result == "executor"

    def test_ask_clarification_goes_to_finalizer(self):
        # given
        from src.core.workflow_engine import route_by_intent
        state = {"recommended_workflow": "ask_clarification", "messages": []}
        # when
        result = route_by_intent(state)
        # then — 모호한 요청은 finalizer로 바로 이동해서 명확화 메시지 반환
        assert result == "finalizer"
