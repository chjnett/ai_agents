# Testing Quick Guide

현재 구현 상태를 빠르게 검증할 때는 아래 순서만 따라가면 됩니다.

## 1) 전체 단위 테스트
```bash
cd /Users/cheonhyeonjun/workspace/06ai_aiagents/my-agent-system
.venv/bin/python3 -m pytest -v
```

## 2) 핵심 모듈만 빠르게 확인
```bash
cd /Users/cheonhyeonjun/workspace/06ai_aiagents/my-agent-system
.venv/bin/python3 -m pytest tests/test_core.py -v
.venv/bin/python3 -m pytest tests/test_cost_guard.py -v
```

## 3) 수동 테스트 (실제 LLM 호출)
```bash
cd /Users/cheonhyeonjun/workspace/06ai_aiagents/my-agent-system
.venv/bin/python3 test_manual.py
```

## 4) 전체 워크플로우 E2E
```bash
cd /Users/cheonhyeonjun/workspace/06ai_aiagents/my-agent-system
.venv/bin/python3 test_manual.py --workflow
```

## 자주 쓰는 옵션
```bash
# 실패한 테스트만 재실행
.venv/bin/python3 -m pytest --lf

# 첫 실패에서 중단
.venv/bin/python3 -m pytest -x

# 간결 출력
.venv/bin/python3 -m pytest -q
```
