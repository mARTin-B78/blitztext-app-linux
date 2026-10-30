"""Streaming the LLM rewrite into the overlay (so you watch the model write).

`llm.chat(..., on_token=cb)` must parse an OpenAI-style SSE stream, hand each
content delta to the callback, and still return the complete text.
"""

import io

import blitztext.llm as llm


def test_read_stream_accumulates_and_calls_back():
    sse = (
        'data: {"choices":[{"delta":{"content":"Hel"}}]}\n'
        "\n"  # keep-alive blank line
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n'
        'data: {"choices":[{"delta":{}}]}\n'        # role-only / empty delta
        ": comment line\n"                           # SSE comment, ignored
        "data: [DONE]\n"
        'data: {"choices":[{"delta":{"content":"X"}}]}\n'  # after DONE -> ignored
    )
    tokens = []
    out = llm._read_stream(io.BytesIO(sse.encode("utf-8")), tokens.append)

    assert out == "Hello"
    assert tokens == ["Hel", "lo"]


def test_read_stream_survives_callback_errors():
    sse = (
        'data: {"choices":[{"delta":{"content":"a"}}]}\n'
        'data: {"choices":[{"delta":{"content":"b"}}]}\n'
        "data: [DONE]\n"
    )

    def boom(_delta):
        raise RuntimeError("UI exploded")

    # A failing UI callback must not break accumulation / delivery.
    out = llm._read_stream(io.BytesIO(sse.encode("utf-8")), boom)
    assert out == "ab"
