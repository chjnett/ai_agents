"""
Model Router — My Agent System

카테고리 기반(v1) + 복잡도 기반(v2) 라우팅을 함께 지원한다.
"""

from __future__ import annotations

import os
from enum import Enum

from langchain_core.language_models import BaseChatModel


class TaskCategory(str, Enum):
    QUICK = "quick"
    DEEP = "deep"
    VISUAL = "visual"
    ULTRABRAIN = "ultrabrain"
    CREATIVE = "creative"
    ANALYSIS = "analysis"


class ComplexityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OrchestrationMode(str, Enum):
    ECONOMY = "economy"
    BALANCED = "balanced"
    POWERFUL = "powerful"


def _has_openai() -> bool:
    return os.getenv("OPENAI_API_KEY", "").strip().startswith("sk-")


def _has_anthropic() -> bool:
    return os.getenv("ANTHROPIC_API_KEY", "").strip().startswith("sk-ant")


def _has_google() -> bool:
    return os.getenv("GOOGLE_API_KEY", "").strip().startswith("AIza")


def _build_model_mapping() -> dict[TaskCategory, str]:
    """
    v1 카테고리 단일 매핑.
    OPENAI_API_KEY는 필수로 유지해 실행 안정성을 보장한다.
    """
    has_openai = _has_openai()
    has_anthropic = _has_anthropic()
    has_google = _has_google()

    if not has_openai:
        raise EnvironmentError(
            "OPENAI_API_KEY가 필요합니다. .env 파일에 'sk-...' 형식의 키를 설정하세요."
        )

    quick_model = "gemini-2.0-flash" if has_google else "gpt-4o-mini"
    deep_model = "gpt-4o"
    visual_model = "gemini-2.0-flash" if has_google else "gpt-4o"
    ultrabrain_model = "gpt-4o"
    creative_model = "claude-haiku-4-5" if has_anthropic else "gpt-4o-mini"
    analysis_model = "gpt-4o-mini"

    return {
        TaskCategory.QUICK: quick_model,
        TaskCategory.DEEP: deep_model,
        TaskCategory.VISUAL: visual_model,
        TaskCategory.ULTRABRAIN: ultrabrain_model,
        TaskCategory.CREATIVE: creative_model,
        TaskCategory.ANALYSIS: analysis_model,
    }


def estimate_complexity(task_description: str) -> ComplexityLevel:
    """규칙 기반 복잡도 추정."""
    desc = task_description.lower()

    high_signals = [
        "architecture",
        "system design",
        "refactor",
        "migration",
        "multi-file",
        "distributed",
        "아키텍처",
        "리팩토링",
        "전체",
        "마이그레이션",
    ]
    low_signals = [
        "typo",
        "one line",
        "rename",
        "small fix",
        "comment",
        "오타",
        "한 줄",
        "간단",
    ]

    if any(token in desc for token in high_signals):
        return ComplexityLevel.HIGH
    if any(token in desc for token in low_signals):
        return ComplexityLevel.LOW
    return ComplexityLevel.MEDIUM


class ModelRouter:
    """
    v1:
      - get_model(category)
      - get_model_for_intent(intent)
    v2:
      - get_model_name_v2(category, task_description)
      - get_model_v2(category, task_description)
    """

    def __init__(self, overrides: dict[str, str] | None = None, verbose: bool = False):
        self.mapping = _build_model_mapping()
        if overrides:
            for key, model in overrides.items():
                try:
                    self.mapping[TaskCategory(key.lower())] = model
                except ValueError:
                    pass
        if verbose:
            print(self.get_mapping_summary())

    def _create_model(self, model_name: str) -> BaseChatModel:
        from langchain_anthropic import ChatAnthropic
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_openai import ChatOpenAI

        low = model_name.lower()
        if "claude" in low:
            return ChatAnthropic(model=model_name)
        if "gemini" in low:
            return ChatGoogleGenerativeAI(model=model_name)
        if "gpt" in low or "o1" in low or "o3" in low:
            return ChatOpenAI(model=model_name)
        return ChatOpenAI(model="gpt-4o-mini")

    # v1 API
    def get_model(self, category: TaskCategory) -> BaseChatModel:
        model_name = self.mapping.get(category, "gpt-4o-mini")
        return self._create_model(model_name)

    def get_model_for_intent(self, intent: str) -> BaseChatModel:
        intent_to_category: dict[str, TaskCategory] = {
            "research": TaskCategory.QUICK,
            "implement": TaskCategory.DEEP,
            "investigate": TaskCategory.ANALYSIS,
            "evaluate": TaskCategory.ULTRABRAIN,
            "fix": TaskCategory.DEEP,
            "generate": TaskCategory.CREATIVE,
        }
        return self.get_model(intent_to_category.get(intent, TaskCategory.QUICK))

    # v2 API
    def get_orchestrated_model(
        self,
        category: TaskCategory,
        task_description: str,
        mode: OrchestrationMode = OrchestrationMode.BALANCED,
    ) -> str:
        """복잡도 추정 후 모드(Economy/Balanced/Powerful)를 적용해 최종 모델명을 결정한다."""
        base_complexity = estimate_complexity(task_description)
        adjusted_complexity = base_complexity

        if mode == OrchestrationMode.ECONOMY:
            if base_complexity == ComplexityLevel.MEDIUM:
                adjusted_complexity = ComplexityLevel.LOW
            elif base_complexity == ComplexityLevel.HIGH:
                adjusted_complexity = ComplexityLevel.MEDIUM
        elif mode == OrchestrationMode.POWERFUL:
            if base_complexity == ComplexityLevel.LOW:
                adjusted_complexity = ComplexityLevel.MEDIUM
            elif base_complexity == ComplexityLevel.MEDIUM:
                adjusted_complexity = ComplexityLevel.HIGH

        matrix = self._build_model_matrix()
        return matrix.get((category, adjusted_complexity), self.mapping.get(category, "gpt-4o-mini"))

    def get_model_name_v2(self, category: TaskCategory, task_description: str) -> str:
        """기존 호환성 유지용"""
        return self.get_orchestrated_model(category, task_description, mode=OrchestrationMode.BALANCED)

    def get_model_v2(
        self,
        category: TaskCategory,
        task_description: str,
        mode: OrchestrationMode = OrchestrationMode.BALANCED,
    ) -> BaseChatModel:
        model_name = self.get_orchestrated_model(category, task_description, mode)
        return self._create_model(model_name)

    def _build_model_matrix(self) -> dict[tuple[TaskCategory, ComplexityLevel], str]:
        """현재 키/예산 상태를 반영한 카테고리 x 복잡도 매트릭스."""
        has_google = _has_google()
        has_anthropic = _has_anthropic()

        deep_low = "gpt-4o-mini"
        deep_medium = "gpt-4o"
        deep_high = "gpt-4o"

        ultrabrain_low = "gpt-4o-mini"
        ultrabrain_medium = "gpt-4o"
        ultrabrain_high = "gpt-4o"

        quick_low = "gemini-2.0-flash" if has_google else "gpt-4o-mini"
        quick_medium = quick_low
        quick_high = "gpt-4o"

        creative_low = "claude-haiku-4-5" if has_anthropic else "gpt-4o-mini"
        creative_medium = "gpt-4o"
        creative_high = "gpt-4o"

        analysis_low = "gpt-4o-mini"
        analysis_medium = "gpt-4o"
        analysis_high = "gpt-4o"

        visual_low = "gemini-2.0-flash" if has_google else "gpt-4o-mini"
        visual_medium = "gemini-2.0-flash" if has_google else "gpt-4o"
        visual_high = "gpt-4o"

        return {
            (TaskCategory.DEEP, ComplexityLevel.LOW): deep_low,
            (TaskCategory.DEEP, ComplexityLevel.MEDIUM): deep_medium,
            (TaskCategory.DEEP, ComplexityLevel.HIGH): deep_high,
            (TaskCategory.ULTRABRAIN, ComplexityLevel.LOW): ultrabrain_low,
            (TaskCategory.ULTRABRAIN, ComplexityLevel.MEDIUM): ultrabrain_medium,
            (TaskCategory.ULTRABRAIN, ComplexityLevel.HIGH): ultrabrain_high,
            (TaskCategory.QUICK, ComplexityLevel.LOW): quick_low,
            (TaskCategory.QUICK, ComplexityLevel.MEDIUM): quick_medium,
            (TaskCategory.QUICK, ComplexityLevel.HIGH): quick_high,
            (TaskCategory.CREATIVE, ComplexityLevel.LOW): creative_low,
            (TaskCategory.CREATIVE, ComplexityLevel.MEDIUM): creative_medium,
            (TaskCategory.CREATIVE, ComplexityLevel.HIGH): creative_high,
            (TaskCategory.ANALYSIS, ComplexityLevel.LOW): analysis_low,
            (TaskCategory.ANALYSIS, ComplexityLevel.MEDIUM): analysis_medium,
            (TaskCategory.ANALYSIS, ComplexityLevel.HIGH): analysis_high,
            (TaskCategory.VISUAL, ComplexityLevel.LOW): visual_low,
            (TaskCategory.VISUAL, ComplexityLevel.MEDIUM): visual_medium,
            (TaskCategory.VISUAL, ComplexityLevel.HIGH): visual_high,
        }

    def get_mapping_summary(self) -> dict[str, str]:
        return {cat.value: model for cat, model in self.mapping.items()}
