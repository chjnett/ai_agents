# My Agent System

> oh-my-openagent 아키텍처를 학습해 Python + LangGraph로 구현한 멀티-에이전트 오케스트레이션 시스템

## 현재 상태

- 핵심 엔진(MVP) 구현 완료: `Intent Router`, `Model Router`, `Workflow Engine`, `Ralph Loop`
- 최신 단위 테스트 상태 (`2026-03-19`): **20 passed / 0 failed**
- 다음 우선순위: **PHASE 1 (CostGuard + Checkpointer + AgentState v2)**

## 빠른 시작

```bash
cd /Users/cheonhyeonjun/workspace/06ai_aiagents/my-agent-system

# 1) 의존성 설치
poetry install

# 2) 환경변수 설정
cp .env.example .env
# .env에 최소 1개 API 키 설정 (예: OPENAI_API_KEY 또는 ANTHROPIC_API_KEY)

# 3) 실행
poetry run python main.py
# 또는 데모
poetry run python main.py --demo
```

## 테스트

테스트는 아래 문서 하나만 보면 됩니다.

- [testing.md](./testing.md)

가장 자주 쓰는 명령:

```bash
# 전체 단위 테스트
.venv/bin/python3 -m pytest -v

# 수동(실제 LLM) 테스트
.venv/bin/python3 test_manual.py

# E2E 워크플로우 테스트
.venv/bin/python3 test_manual.py --workflow
```

## 아키텍처 요약

```text
사용자 요청
  -> Intent Gate
    -> research_only/direct: Executor
    -> plan_execute: Planner -> Executor -> Reviewer -> Loop Check
                                                 | continue -> Executor
                                                 | done     -> Finalizer
```

핵심 파일:

- `src/core/intent_router.py`: 의도 분류
- `src/core/model_router.py`: 카테고리 기반 모델 선택
- `src/core/workflow_engine.py`: LangGraph 오케스트레이션
- `main.py`: CLI 진입점

## 문서

- `docs/ARCHITECTURE.md`: v1 설계
- `docs/ARCHITECTURE_V2.md`: v2 고도화 설계
- `docs/CODE_DEEP_DIVE.md`: 코드 분석/개선 포인트
- `docs/TESTING_GUIDE.md`: 상세 테스트 가이드

## 로드맵

- [x] Intent Router
- [x] Model Router
- [x] LangGraph 기본 워크플로우
- [x] Ralph Loop
- [ ] PHASE 1: 안전장치 & 상태 영속성
- [ ] PHASE 2: 에이전트 클래스 분리
- [ ] PHASE 3: Dynamic Tool Discovery
- [ ] PHASE 4+: HITL, Observability, 병렬 실행, 메모리, API
