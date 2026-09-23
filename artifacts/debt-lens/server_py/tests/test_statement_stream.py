"""A large bank statement must use streaming and must not save truncated output."""

import json
import os
import sys
from types import SimpleNamespace

import pytest

SERVER_PY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVER_PY_DIR not in sys.path:
    sys.path.insert(0, SERVER_PY_DIR)

import admin_routes  # noqa: E402


class FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get_final_message(self):
        return self.message


class FakeMessages:
    def __init__(self, message):
        self.message = message
        self.calls = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self.message)

    def create(self, **kwargs):
        raise AssertionError("32,000-token extraction must not use non-streaming create")


def _fake_message(data, stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(data))],
        stop_reason=stop_reason,
    )


def test_bank_statement_uses_stream_and_parses_complete_response(monkeypatch):
    data = {"transactions": [{"date": "2026-01-01", "amount": 123, "type": "credit"}]}
    messages = FakeMessages(_fake_message(data))
    monkeypatch.setattr(admin_routes, "anthropic_client", SimpleNamespace(messages=messages))

    result = admin_routes._extract_statement_data({"type": "document"}, "bank")

    assert result == data
    assert messages.calls[0]["max_tokens"] == 32000
    assert messages.calls[0]["messages"][0]["content"][1] == {"type": "document"}


def test_truncated_statement_is_never_treated_as_complete(monkeypatch):
    messages = FakeMessages(_fake_message({"transactions": []}, stop_reason="max_tokens"))
    monkeypatch.setattr(admin_routes, "anthropic_client", SimpleNamespace(messages=messages))

    with pytest.raises(ValueError, match="incomplete"):
        admin_routes._extract_statement_data({"type": "document"}, "bank")