from __future__ import annotations

import json

import pytest

from core.services import notifier


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_notify_noop_without_webhooks_configured(monkeypatch):
    calls = []
    monkeypatch.setattr(
        notifier.urllib.request, "urlopen", lambda *a, **k: calls.append(a)
    )

    notifier.notify({}, "schedule.failed", {"status": "boom"})

    assert calls == []


def test_notify_posts_to_each_configured_webhook(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout=None):
        requests.append(request)
        return _FakeResponse()

    monkeypatch.setattr(notifier.urllib.request, "urlopen", fake_urlopen)

    config = {
        "notifications": {
            "webhooks": ["https://example.com/a", "https://example.com/b"]
        }
    }
    notifier.notify(config, "schedule.failed", {"status": "failed: boom"})

    assert [r.full_url for r in requests] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    body = json.loads(requests[0].data.decode("utf-8"))
    assert body == {"event": "schedule.failed", "status": "failed: boom"}


def test_notify_accepts_single_url_string(monkeypatch):
    requests = []
    monkeypatch.setattr(
        notifier.urllib.request,
        "urlopen",
        lambda request, timeout=None: requests.append(request) or _FakeResponse(),
    )

    notifier.notify(
        {"notifications": {"webhooks": "https://example.com/only"}},
        "schedule.failed",
        {},
    )

    assert len(requests) == 1
    assert requests[0].full_url == "https://example.com/only"


def test_notify_swallows_delivery_errors(monkeypatch):
    def raise_error(request, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(notifier.urllib.request, "urlopen", raise_error)

    # Must not raise even though every webhook fails to deliver.
    notifier.notify(
        {"notifications": {"webhooks": ["https://example.com/a"]}},
        "schedule.failed",
        {"status": "failed"},
    )


@pytest.mark.parametrize(
    "status,expected",
    [
        ("started", False),
        ("completed", False),
        ("success", False),
        ("skipped: already_running", False),
        ("workspace_required", True),
        ("workspace_unregistered", True),
        ("task_not_found", True),
        ("failed: boom", True),
    ],
)
def test_is_failure_status(status, expected):
    from core.services.scheduler_loop import _is_failure_status

    assert _is_failure_status(status) is expected
