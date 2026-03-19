"""
Model Router — My Agent System

API 키 보유 현황에 따라 자동으로 최적 모델을 배정한다.

예산 전략:
  - OpenAI:    토큰 충분 → 심층 작업(DEEP, ULTRABRAIN, ANALYSIS) 메인 담당
  - Google:    무료 티어 (gemini-2.0-flash) → 빠른 작업(QUICK, VISUAL) 무료 처리
  - Anthropic: 선택 추가 (Claude Haiku는 저렴) → 창작(CREATIVE) 강점
  - 키 없는 프로바이더는 자동으로 OpenAI fallback
"""

import os
from enum import Enum
from functools import lru_cache

from langchain_core.language_models import BaseChatModel


# ─────────────────────────────────────────────
# 1. 카테고리 정의
# ─────────────────────────────────────────────

class TaskCategory(str, Enum):
    """
    oh-my-openagent의 카테고리 시스템.
    에이전트는 카테고리를 지정하고, 라우터가 최적 모델을 선택한다.
    """
    QUICK      = "quick"       # 단순·빠른 작업 (요약, 분류, 단순 답변)
    DEEP       = "deep"        # 심층 자율 작업 (복잡한 코딩, 아키텍처)
    VISUAL     = "visual"      # 시각/멀티모달 (이미지 분석, UI 피드백)
    ULTRABRAIN = "ultrabrain"  # 최고 난이도 추론 (수학, 논리, 중요 결정)
    CREATIVE   = "creative"    # 창작, 글쓰기, 마케팅 카피
    ANALYSIS   = "analysis"    # 데이터 분석, 패턴 인식, 코드 리뷰


# ─────────────────────────────────────────────
# 2. API 키 감지
# ─────────────────────────────────────────────

def _has_openai() -> bool:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return key.startswith("sk-")

def _has_anthropic() -> bool:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    return key.startswith("sk-ant")

def _has_google() -> bool:
    key = os.getenv("GOOGLE_API_KEY", "").strip()
    return key.startswith("AIza")


# ─────────────────────────────────────────────
# 3. 예산 인식 모델 매핑 빌더
# ─────────────────────────────────────────────

def _build_model_mapping() -> dict[TaskCategory, str]:
    """
    보유한 API 키와 예산 전략에 따라 카테고리→모델 매핑을 동적으로 생성한다.

    예산 전략:
    ┌──────────────┬──────────────────────────────────────────────────────────┐
    │ QUICK        │ Google Gemini Flash (무료) → OpenAI mini fallback         │
    │ DEEP         │ OpenAI GPT-4o (심층 코딩 강점, 토큰 충분)                 │
    │ VISUAL       │ Google Gemini Flash (무료, 멀티모달 강점)                  │
    │ ULTRABRAIN   │ OpenAI GPT-4o (최고 추론 강점)                            │
    │ CREATIVE     │ Claude Haiku (창작 강점, 저렴) → GPT-4o-mini fallback     │
    │ ANALYSIS     │ OpenAI GPT-4o-mini (분석, 비용 효율)                      │
    └──────────────┴──────────────────────────────────────────────────────────┘
    """
    has_openai    = _has_openai()
    has_anthropic = _has_anthropic()
    has_google    = _has_google()

    # 공통 fallback: OpenAI가 없으면 시스템 자체가 작동 불가
    if not has_openai:
        raise EnvironmentError(
            "OPENAI_API_KEY가 필요합니다. .env 파일에 'sk-...' 형식의 키를 설정하세요."
        )

    # ── QUICK: 빠르고 저렴한 분류·요약 ───────────────────────────
    # Gemini Flash 무료 > Claude Haiku 저렴 > GPT-4o-mini
    if has_google:
        quick_model = "gemini-2.0-flash"       # 무료
    elif has_anthropic:
        quick_model = "claude-haiku-4-5"       # $0.25/1M (매우 저렴)
    else:
        quick_model = "gpt-4o-mini"            # OpenAI 저가

    # ── DEEP: 복잡한 코딩·아키텍처 ──────────────────────────────
    # GPT-4o는 코드 이해·생성에서 균형적으로 강함
    deep_model = "gpt-4o"                      # OpenAI (토큰 충분)

    # ── VISUAL: 이미지·멀티모달 ──────────────────────────────────
    # Gemini의 핵심 강점 + 무료 티어
    if has_google:
        visual_model = "gemini-2.0-flash"      # 무료, 멀티모달 강점
    else:
        visual_model = "gpt-4o"               # GPT-4o도 vision 지원

    # ── ULTRABRAIN: 최고 난이도 추론 ─────────────────────────────
    # GPT-4o = 현재 범용 추론 최강급
    ultrabrain_model = "gpt-4o"               # OpenAI (토큰 충분)

    # ── CREATIVE: 창작·글쓰기 ────────────────────────────────────
    # Claude는 창작 품질이 높지만 비용 있음
    # Haiku는 저렴하므로 Anthropic 키가 있으면 사용
    if has_anthropic:
        creative_model = "claude-haiku-4-5"   # 창작 강점 + 저렴
    else:
        creative_model = "gpt-4o-mini"        # 저렴한 creative fallback

    # ── ANALYSIS: 데이터 분석·패턴 인식 ─────────────────────────
    # GPT-4o-mini: 분석엔 충분하면서 비용 절감
    analysis_model = "gpt-4o-mini"            # OpenAI 저가 (분석엔 충분)

    mapping = {
        TaskCategory.QUICK:      quick_model,
        TaskCategory.DEEP:       deep_model,
        TaskCategory.VISUAL:     visual_model,
        TaskCategory.ULTRABRAIN: ultrabrain_model,
        TaskCategory.CREATIVE:   creative_model,
        TaskCategory.ANALYSIS:   analysis_model,
    }

    return mapping


def _describe_mapping(mapping: dict[TaskCategory, str]) -> str:
    """현재 모델 배정 현황을 사람이 읽기 좋은 형태로 출력"""
    lines = ["\n  현재 모델 배정 현황:"]
    providers = {
        "openai":    ("OpenAI",    "✅ 유료 (토큰 충분)"),
        "anthropic": ("Anthropic", "✅ 있음" if _has_anthropic() else "❌ 키 없음 (OpenAI fallback)"),
        "google":    ("Google",    "✅ 무료 티어" if _has_google() else "❌ 키 없음 (OpenAI fallback)"),
    }
    for pid, (name, status) in providers.items():
        lines.append(f"    {name}: {status}")
    lines.append("")
    for cat, model in mapping.items():
        lines.append(f"    {cat.value:<12} → {model}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# 4. ModelRouter 클래스
# ─────────────────────────────────────────────

class ModelRouter:
    """
    태스크 카테고리에 따라 최적 LLM을 선택한다.

    - API 키 보유 현황을 자동 감지해서 예산에 맞는 모델 배정
    - OpenAI 중심, Gemini 무료 티어 활용, Anthropic 선택적
    - 키 없는 프로바이더는 자동으로 OpenAI fallback
    """

    def __init__(self, overrides: dict[str, str] | None = None, verbose: bool = False):
        """
        Args:
            overrides: 카테고리별 모델 수동 오버라이드
                       예: {"quick": "gpt-4o-mini", "deep": "gpt-4o"}
            verbose:   True이면 시작 시 현재 모델 배정 현황 출력
        """
        self.mapping = _build_model_mapping()

        if overrides:
            for key, model in overrides.items():
                try:
                    self.mapping[TaskCategory(key.lower())] = model
                except ValueError:
                    pass

        if verbose:
            print(_describe_mapping(self.mapping))

    def get_model(self, category: TaskCategory) -> BaseChatModel:
        """카테고리에 맞는 LLM 인스턴스를 반환한다."""
        model_name = self.mapping.get(category, "gpt-4o-mini")
        return self._create_model(model_name)

    def _create_model(self, model_name: str) -> BaseChatModel:
        """모델 이름으로 알맞은 LangChain LLM 인스턴스를 생성한다."""
        from langchain_anthropic import ChatAnthropic
        from langchain_openai import ChatOpenAI
        from langchain_google_genai import ChatGoogleGenerativeAI

        name_lower = model_name.lower()

        if "claude" in name_lower:
            return ChatAnthropic(model=model_name)
        elif "gemini" in name_lower:
            return ChatGoogleGenerativeAI(model=model_name)
        elif "gpt" in name_lower or "o1" in name_lower or "o3" in name_lower:
            return ChatOpenAI(model=model_name)
        else:
            # 마지막 fallback: OpenAI 저가 모델
            return ChatOpenAI(model="gpt-4o-mini")

    def get_model_for_intent(self, intent: str) -> BaseChatModel:
        """
        의도 타입 → 카테고리 → 모델 자동 선택.
        IntentRouter와 연동.
        """
        intent_to_category: dict[str, TaskCategory] = {
            "research":    TaskCategory.QUICK,       # 정보 수집 → 빠른 모델
            "implement":   TaskCategory.DEEP,        # 구현 → 심층 모델
            "investigate": TaskCategory.ANALYSIS,    # 분석 → 분석 모델
            "evaluate":    TaskCategory.ULTRABRAIN,  # 평가 → 최고 모델
            "fix":         TaskCategory.DEEP,        # 수정 → 심층 모델
            "generate":    TaskCategory.CREATIVE,    # 창작 → 창작 모델
        }
        category = intent_to_category.get(intent, TaskCategory.QUICK)
        return self.get_model(category)

    def get_mapping_summary(self) -> dict[str, str]:
        """현재 카테고리→모델명 매핑을 문자열 dict으로 반환 (로깅/디버깅용)"""
        return {cat.value: model for cat, model in self.mapping.items()}
