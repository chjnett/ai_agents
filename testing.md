# Testing Quick Guide

직접 테스트할 때 아래 3개만 실행하면 됩니다.

## 1) 단위 테스트 (가장 먼저)
```bash
cd /Users/cheonhyeonjun/workspace/06ai_aiagents/my-agent-system
.venv/bin/python3 -m pytest -v
```

## 2) 수동 테스트 (실제 LLM 호출)
```bash
cd /Users/cheonhyeonjun/workspace/06ai_aiagents/my-agent-system
.venv/bin/python3 test_manual.pypip install -U google-generativeai
```

## 3) 전체 워크플로우 E2E
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
```
