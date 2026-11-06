from radar import llm


def test_ai_json_falls_back_to_gemini(monkeypatch):
    monkeypatch.setenv("GCP_SA_KEY", "{}")
    monkeypatch.setattr(llm, "_claude_down", [False])

    class E(Exception):
        status_code = 404

    def boom(prompt, timeout=600):
        raise E("model not enabled")
    monkeypatch.setattr(llm, "claude_json", boom)
    monkeypatch.setattr(llm, "gemini_json", lambda p, temperature=0.6, timeout=120: {"ok": 1})
    d = llm.ai_json("x", quality=True)
    assert d["ok"] == 1 and d["_model"].startswith("gemini")
    assert llm._claude_down[0] is True          # 4xx → 이번 실행 동안 Claude 재시도 안 함


def test_ai_json_uses_claude_when_ok(monkeypatch):
    monkeypatch.setenv("GCP_SA_KEY", "{}")
    monkeypatch.setattr(llm, "_claude_down", [False])
    monkeypatch.setattr(llm, "claude_json", lambda p, timeout=600: {"ok": 2})
    assert llm.ai_json("x", quality=True)["_model"] == "claude-opus-5-5"


def test_extract_json_handles_fences():
    assert llm._extract_json('```json\n{"a": 1}\n```') == {"a": 1}
