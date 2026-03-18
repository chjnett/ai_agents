"""
Intent Router — My Agent System

oh-my-openagent의 Intent Gate를 Python으로 구현.
모든 요청은 반드시 이 분류기를 통과한다.

개선 이력:
- v1: regex JSON 파싱 방식
- v2: with_structured_output() 으로 파싱 완전 제거
      UNCLEAR 인텐트 추가, Confidence Guardrail, chat_history 문맥 지원
"""

from enum import Enum
from typing import Sequence

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# 1. 타입 정의
# ─────────────────────────────────────────────

class IntentType(str, Enum):
    RESEARCH    = "research"     # 조사, 이해, 정보 수집
    IMPLEMENT   = "implement"    # 구현, 생성, 코딩 (명시적 요청)
    INVESTIGATE = "investigate"  # 분석, 확인, 디버그
    EVALUATE    = "evaluate"     # 평가, 의견 제시
    FIX         = "fix"          # 버그 수정, 오류 해결
    GENERATE    = "generate"     # 문서, 보고서, 요약 생성
    UNCLEAR     = "unclear"      # 모호하거나 복합 의도 → 명확화 요청


class RoutingDecision(BaseModel):
    """IntentRouter의 반환 타입. with_structured_output()으로 자동 채워진다."""

    intent: IntentType = Field(
        description="가장 적합한 의도 카테고리"
    )
    confidence: float = Field(
        description="판단의 확신도 (0.0 ~ 1.0)",
        ge=0.0,
        le=1.0,
    )
    reasoning: str = Field(
        description="이 의도로 판단한 논리적 근거 (1~2문장)"
    )
    recommended_workflow: str = Field(
        description=(
            "실행할 워크플로우 타입. "
            "plan_execute | direct | research_only | ask_clarification 중 하나"
        )
    )
    suggested_agents: list[str] = Field(
        description="이 작업에 투입할 에이전트 목록 (researcher, coder, writer, analyst 등)"
    )


# ─────────────────────────────────────────────
# 2. 분류 프롬프트 (모듈 상수 — 매 호출 재생성 방지)
# ─────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an intent classifier for a multi-agent AI system.
Analyze the user's CURRENT request and any RECENT CHAT HISTORY to determine the true intent.
Always consider context: a follow-up message may only make sense in light of the prior conversation.

# Intent Types
- research:    Understanding/learning ("explain X", "how does Y work", "what is Z")
- implement:   Explicit build/create request ("add X", "create Y", "implement Z")
- investigate: Analyze/debug existing things ("look into X", "check Y", "what happened")
- evaluate:    Opinion/assessment ("what do you think about", "review this")
- fix:         Problem solving ("error X", "broken", "not working", "fix")
- generate:    Content creation ("write a report", "summarize", "draft")
- unclear:     Request is too vague, lacks context, or contains multiple conflicting intents

# Workflow Mapping
- research    → research_only     (find and synthesize information only)
- implement   → plan_execute      (plan first, then build step by step)
- investigate → direct            (analyze and report findings)
- evaluate    → direct            (assess and advise)
- fix         → plan_execute      (diagnose, then fix)
- generate    → direct            (generate content directly)
- unclear     → ask_clarification (ask user to clarify before proceeding)

# Examples
User: "Make a login page using Next.js"
→ intent: implement | workflow: plan_execute | agents: [coder]

User: "It's returning a 500 error" (history shows they were working on a FastAPI server)
→ intent: fix | workflow: plan_execute | agents: [coder, analyst]

User: "Do both research on Apple stock AND build a trading bot"
→ intent: unclear | workflow: ask_clarification
  (reasoning: Multiple distinct complex intents in one request)

User: "Can you help me?"
→ intent: unclear | workflow: ask_clarification
  (reasoning: Too vague — no actionable information)
"""

_CLASSIFICATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM_PROMPT),
    MessagesPlaceholder(variable_name="chat_history", optional=True),
    ("human", "{user_request}"),
])

# Confidence Guardrail 임계값
_CONFIDENCE_THRESHOLD = 0.65


# ─────────────────────────────────────────────
# 3. IntentRouter 클래스
# ─────────────────────────────────────────────

class IntentRouter:
    """
    with_structured_output()을 활용해 regex 파싱 없이
    Pydantic 객체를 직접 반환하는 분류기.

    개선 포인트:
    - regex JSON 파싱 완전 제거 (with_structured_output)
    - chat_history: list[BaseMessage] 로 대화 문맥 지원
    - Confidence Guardrail: 확신도 낮으면 ask_clarification으로 전환
    - temperature=0: 분류 작업은 결정론적이어야 함
    - 포괄적 에러 처리: API 실패도 안전하게 처리
    """

    def __init__(self, model_name: str = "claude-haiku-4-5"):
        # temperature=0: 분류는 창의성이 아닌 일관성이 필요
        base_llm = ChatAnthropic(model=model_name, temperature=0)

        # with_structured_output: LLM이 RoutingDecision 스키마를 직접 채워 반환
        # regex로 JSON을 파싱하던 취약한 로직을 완전히 대체
        self.chain = _CLASSIFICATION_PROMPT | base_llm.with_structured_output(RoutingDecision)

    async def classify(
        self,
        user_request: str,
        chat_history: Sequence[BaseMessage] | None = None,
    ) -> RoutingDecision:
        """
        사용자 요청을 분류하고 라우팅 결정을 반환한다.

        Args:
            user_request:  사용자의 현재 요청 텍스트
            chat_history:  이전 대화 이력 (BaseMessage 리스트).
                           None이거나 빈 리스트면 문맥 없이 분류.

        Returns:
            RoutingDecision: 의도, 확신도, 권장 워크플로우, 제안 에이전트
        """
        try:
            decision: RoutingDecision = await self.chain.ainvoke({
                "user_request": user_request,
                "chat_history": list(chat_history) if chat_history else [],
            })

            # ── Confidence Guardrail ──────────────────────────────
            # 확신도가 낮거나 LLM 스스로 UNCLEAR로 분류한 경우
            # 직접 mutation 대신 새 객체 생성 (Pydantic 안전 패턴)
            if decision.confidence < _CONFIDENCE_THRESHOLD or decision.intent == IntentType.UNCLEAR:
                return RoutingDecision(
                    intent=IntentType.UNCLEAR,
                    confidence=decision.confidence,
                    reasoning=(
                        f"요청이 모호하거나 여러 의도가 섞여 있어 사용자의 명확한 지시가 필요합니다. "
                        f"(원본 판단: {decision.reasoning})"
                    ),
                    recommended_workflow="ask_clarification",
                    suggested_agents=[],
                )

            return decision

        except Exception as e:
            # API 에러, 네트워크 실패, 스키마 불일치 등 모든 예외 처리
            # 절대 예외를 상위로 전파하지 않는다 — 워크플로우가 멈추면 안 됨
            return RoutingDecision(
                intent=IntentType.UNCLEAR,
                confidence=0.0,
                reasoning=f"Classification system error: {type(e).__name__}: {e}",
                recommended_workflow="ask_clarification",
                suggested_agents=[],
            )

    def classify_sync(
        self,
        user_request: str,
        chat_history: Sequence[BaseMessage] | None = None,
    ) -> RoutingDecision:
        """동기 버전 (테스트 및 CLI에서 사용)"""
        import asyncio
        return asyncio.run(self.classify(user_request, chat_history))
