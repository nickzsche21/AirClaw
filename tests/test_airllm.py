"""AirLLM prompt construction. 2.x hardcoded Llama-2 [INST] for every model."""

from airclaw.backends.airllm import AirLLMBackend, resolve_alias


class TemplateTokenizer:
    """Stands in for a HF tokenizer that ships a chat template."""
    chat_template = "{{ real }}"

    def __init__(self):
        self.seen = None

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        self.seen = messages
        body = "".join(f"<|{m['role']}|>{m['content']}" for m in messages)
        return body + ("<|assistant|>" if add_generation_prompt else "")


class PlainTokenizer:
    chat_template = None


def backend_with(tok):
    b = AirLLMBackend("qwen")
    b._model = type("M", (), {"tokenizer": tok})()
    return b


def test_uses_model_chat_template_when_present():
    tok = TemplateTokenizer()
    b = backend_with(tok)
    out = b.build_prompt([{"role": "system", "content": "be terse"},
                          {"role": "user", "content": "hi"}])
    assert out == "<|system|>be terse<|user|>hi<|assistant|>"
    # No Llama-2 syntax leaking into a Qwen prompt.
    assert "[INST]" not in out


def test_falls_back_when_no_template():
    b = backend_with(PlainTokenizer())
    out = b.build_prompt([{"role": "user", "content": "hi"}])
    assert "User: hi" in out
    assert out.rstrip().endswith("Assistant:")


def test_falls_back_when_template_raises():
    class Broken(TemplateTokenizer):
        def apply_chat_template(self, *a, **k):
            raise ValueError("no template for this role order")
    b = backend_with(Broken())
    out = b.build_prompt([{"role": "user", "content": "hi"}])
    assert "User: hi" in out


def test_flattens_structured_content():
    tok = TemplateTokenizer()
    b = backend_with(tok)
    b.build_prompt([{"role": "user",
                     "content": [{"type": "text", "text": "a"},
                                 {"type": "text", "text": "b"}]}])
    assert tok.seen[0]["content"] == "ab"


def test_aliases_resolve():
    assert resolve_alias("coder") == "Qwen/Qwen2.5-Coder-7B-Instruct"
    assert resolve_alias("org/custom-model") == "org/custom-model"
    assert resolve_alias(None)


def test_generate_before_load_raises_clearly():
    b = AirLLMBackend("coder")
    try:
        b.generate([{"role": "user", "content": "hi"}], 10, 0.7)
    except RuntimeError as exc:
        assert "loading" in str(exc).lower()
    else:
        raise AssertionError("expected RuntimeError")
