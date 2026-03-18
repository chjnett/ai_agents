from enum import Enum
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.language_models import BaseChatModel


class TaskCategory(str, Enum):
    """
    oh-my-openagent의 카테고리 시스템을 Python으로 구현.
    에이전트는 모델 이름 대신 카테고리를 지정하고,
    라우터가 자동으로 최적 모델을 선택한다.
    """
    QUICK      = "quick"       # 단순 빠른 작업 (요약, 분류, 단순 답변)
    DEEP       = "deep"        # 심층 자율 작업 (복잡한 코딩, 아키텍처)
    VISUAL     = "visual"      # 시각/프론트엔드 작업
    ULTRABRAIN = "ultrabrain"  # 가장 어려운 추론 (수학, 논리, 아키텍처 결정)
    CREATIVE   = "creative"    # 창작, 글쓰기, 마케팅
    ANALYSIS   = "analysis"    # 데이터 분석, 패턴 인식


# 카테고리 → 기본 모델 매핑
# 각 모델의 강점에 맞게 배치 (oh-my-openagent 철학)
MODEL_CATEGORY_MAPPING: dict[TaskCategory, str] = {
    TaskCategory.QUICK:      "claude-haiku-4-5",      # 빠르고 저렴
    TaskCategory.DEEP:       "claude-opus-4-6",        # 자율 심층 작업
    TaskCategory.VISUAL:     "gemini-2.5-pro",         # Gemini = 비전 강점
    TaskCategory.ULTRABRAIN: "gpt-4o",                 # GPT = 추론 강점
    TaskCategory.CREATIVE:   "claude-sonnet-4-6",      # Claude = 창작 강점
    TaskCategory.ANALYSIS:   "gpt-4o",                 # GPT = 분석 강점
}

# 폴백 체인: 기본 모델 실패 시 순서대로 시도
FALLBACK_CHAIN: list[str] = [
    "claude-opus-4-6",
    "gpt-4o",
    "gemini-2.5-pro",
    "claude-sonnet-4-6",
]


class ModelRouter:
    """
    태스크 카테고리에 따라 최적 LLM을 선택한다.
    oh-my-openagent의 카테고리 기반 모델 라우팅을 Python으로 구현.
    """

    def __init__(self, overrides: dict[str, str] | None = None):
        """
        Args:
            overrides: 카테고리별 모델 커스터마이징
                       예: {"quick": "claude-haiku-4-5", "ultrabrain": "gpt-4o"}
        """
        self.mapping = {**MODEL_CATEGORY_MAPPING}
        if overrides:
            for category, model in overrides.items():
                if category in TaskCategory.__members__:
                    self.mapping[TaskCategory(category)] = model

    def get_model(self, category: TaskCategory) -> BaseChatModel:
        """카테고리에 맞는 LLM 인스턴스를 반환한다."""
        model_name = self.mapping.get(category, "claude-haiku-4-5")
        return self._create_model(model_name)

    def _create_model(self, model_name: str) -> BaseChatModel:
        """모델 이름으로 LangChain LLM 인스턴스 생성"""
        name_lower = model_name.lower()

        if "claude" in name_lower:
            return ChatAnthropic(model=model_name)
        elif "gpt" in name_lower or "o1" in name_lower or "o3" in name_lower:
            return ChatOpenAI(model=model_name)
        elif "gemini" in name_lower:
            return ChatGoogleGenerativeAI(model=model_name)
        else:
            # 기본값: Claude Haiku (가장 저렴)
            return ChatAnthropic(model="claude-haiku-4-5")

    def get_model_for_intent(self, intent: str) -> BaseChatModel:
        """
        의도 타입에 따라 카테고리를 결정하고 모델을 반환.
        IntentRouter와 연동.
        """
        intent_to_category = {
            "research":    TaskCategory.QUICK,       # 리서치는 빠른 모델로
            "implement":   TaskCategory.DEEP,         # 구현은 심층 모델로
            "investigate": TaskCategory.ANALYSIS,     # 분석은 분석 모델로
            "evaluate":    TaskCategory.ULTRABRAIN,   # 평가는 최고 모델로
            "fix":         TaskCategory.DEEP,         # 수정은 심층 모델로
            "generate":    TaskCategory.CREATIVE,     # 생성은 창작 모델로
        }
        category = intent_to_category.get(intent, TaskCategory.QUICK)
        return self.get_model(category)
