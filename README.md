# My Agent System

> oh-my-openagent 아키텍처를 학습하고, Python + LangGraph로 나만의 버전을 구현한 멀티-에이전트 시스템

## 아키텍처

```
사용자 요청
    │
    ▼
Intent Gate (의도 분류)
    │
    ├── research_only → Executor (직접 답변)
    ├── direct       → Executor (직접 실행)
    └── plan_execute → Planner → Executor → Reviewer → Loop Check
                                                            │
                                                    ┌───────┴───────┐
                                                 continue         done
                                                    │               │
                                                 Executor      Finalizer
```

## oh-my-openagent에서 가져온 패턴

| 개념            | 원본 (TypeScript)                     | 이 프로젝트 (Python)                       |
| --------------- | ------------------------------------- | ------------------------------------------ |
| Intent Gate     | `sisyphus.ts` Phase 0                 | `intent_router.py`                         |
| 카테고리 라우팅 | `delegate-task/constants.ts`          | `model_router.py`                          |
| Ralph Loop      | `ralph-loop/loop-state-controller.ts` | `workflow_engine.py::should_continue_loop` |
| Oracle 패턴     | `oracle.ts` (읽기 전용 리뷰어)        | `reviewer_node()`                          |
| Factory 패턴    | `createXXXAgent()`                    | `build_orchestration_graph()`              |

## 빠른 시작

```bash
# 1. 의존성 설치
poetry install

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일에 ANTHROPIC_API_KEY 입력

# 3. 실행
python main.py        # 대화형 CLI
python main.py --demo # 데모 모드
```

## 프로젝트 구조

```
my-agent-system/
├── src/
│   ├── core/
│   │   ├── intent_router.py    # Intent Gate 구현
│   │   ├── model_router.py     # 카테고리 기반 모델 선택
│   │   └── workflow_engine.py  # LangGraph 오케스트레이션
│   └── agents/                 # (추가 예정)
├── tests/
│   └── test_core.py
├── main.py
├── pyproject.toml
└── .env.example
```

## 로드맵

- [x] Intent Router (의도 분류기)
- [x] Model Router (카테고리 기반 모델 선택)
- [x] LangGraph 기본 워크플로우
- [x] Ralph Loop 로직
- [ ] 전용 에이전트 클래스 (Researcher, Coder, Writer)
- [ ] Tool Registry (Web Search, Code Executor)
- [ ] FastAPI REST API
- [ ] Redis 세션 저장
- [ ] LangFuse 관찰 가능성 통합
- [ ] RAG Knowledge Base 통합
