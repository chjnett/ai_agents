from enum import Enum
from pydantic import BaseModel
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
import json
import re


class IntentType(str, Enum):
    RESEARCH    = "research"      # 조사, 이해, 정보 수집
    IMPLEMENT   = "implement"     # 구현, 생성, 코딩 (명시적 요청)
    INVESTIGATE = "investigate"   # 분석, 확인, 디버그
    EVALUATE    = "evaluate"      # 평가, 의견 제시
    FIX         = "fix"           # 버그 수정, 오류 해결
    GENERATE    = "generate"      # 문서, 보고서, 요약 생성


class RoutingDecision(BaseModel):
    intent: IntentType
    confidence: float
    reasoning: str
    recommended_workflow: str   # "plan_execute" | "direct" | "research_only"
    suggested_agents: list[str]


INTENT_CLASSIFICATION_PROMPT = """\
You are an intent classifier for a multi-agent AI system.

Analyze the user's request and determine the true intent.

# Intent Types
- research: Understanding/learning ("explain X", "how does Y work", "what is Z")
- implement: Explicit build/create request ("add X", "create Y", "implement Z")
- investigate: Analyze/debug existing things ("look into X", "check Y", "what happened")
- evaluate: Opinion/assessment ("what do you think about", "review this")
- fix: Problem solving ("error X", "broken", "not working", "fix")
- generate: Content creation ("write a report", "summarize", "draft")

# Workflow Recommendations
- research → "research_only" (just find and synthesize)
- implement → "plan_execute" (plan first, then build)
- investigate → "direct" (analyze and report)
- evaluate → "direct" (assess and advise)
- fix → "plan_execute" (diagnose then fix)
- generate → "direct" (generate directly)

Return ONLY valid JSON, no explanation:
{{
  "intent": "<intent_type>",
  "confidence": <0.0-1.0>,
  "reasoning": "<one brief sentence>",
  "recommended_workflow": "<plan_execute|direct|research_only>",
  "suggested_agents": ["<agent1>", "<agent2>"]
}}

User request: {user_request}
"""


class IntentRouter:
    """
    oh-my-openagent의 Intent Gate를 Python으로 구현.
    모든 요청은 반드시 이 분류기를 통과한다.
    """

    def __init__(self, model_name: str = "claude-haiku-4-5"):
        # 분류에는 가장 빠르고 저렴한 모델 사용 (oh-my-openagent 원칙)
        self.llm = ChatAnthropic(model=model_name)
        self.prompt = ChatPromptTemplate.from_template(INTENT_CLASSIFICATION_PROMPT)
        self.chain = self.prompt | self.llm

    async def classify(self, user_request: str) -> RoutingDecision:
        """
        사용자 요청을 분류하고 라우팅 결정을 반환한다.

        Args:
            user_request: 사용자의 원본 요청 텍스트

        Returns:
            RoutingDecision: 의도 타입, 권장 워크플로우, 제안 에이전트
        """
        response = await self.chain.ainvoke({"user_request": user_request})
        raw = response.content.strip()

        # JSON 블록 추출 (```json ... ``` 형태로 올 수도 있음)
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            # 분류 실패 시 기본값 반환
            return RoutingDecision(
                intent=IntentType.RESEARCH,
                confidence=0.5,
                reasoning="Classification failed, defaulting to research",
                recommended_workflow="research_only",
                suggested_agents=["researcher"],
            )

        data = json.loads(json_match.group())
        return RoutingDecision(**data)

    def classify_sync(self, user_request: str) -> RoutingDecision:
        """동기 버전 (CLI에서 사용)"""
        import asyncio
        return asyncio.run(self.classify(user_request))
