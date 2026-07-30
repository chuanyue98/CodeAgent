"""Tests for language resolution and the message table.

``config.json`` carried a ``language`` field that nothing read, so user-facing
output was a fixed mix of English and Chinese. These cover the resolution
order that makes the setting real.
"""

from __future__ import annotations

import json

import pytest

from core import i18n


@pytest.fixture(autouse=True)
def reset_language(monkeypatch):
    """Each test resolves from scratch; the module caches after first use."""
    monkeypatch.delenv(i18n.ENV_VAR, raising=False)
    i18n.set_language(None)
    yield
    i18n.set_language(None)


# --- normalization -----------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("en", "en"),
        ("zh", "zh"),
        ("ZH", "zh"),
        (" en ", "en"),
        ("zh-CN", "zh"),
        ("zh_CN", "zh"),
        ("en-US", "en"),
        ("zh-Hans", "zh"),
    ],
)
def test_normalize_accepts_locale_forms(value, expected):
    assert i18n._normalize(value) == expected


@pytest.mark.parametrize("value", ["", None, "auto", "system", "hybrid", "fr", "xx-YY"])
def test_normalize_rejects_auto_and_unsupported(value):
    """'hybrid' is the legacy value from when the setting was inert; it must
    read as "decide for me" rather than blow up on configs already on disk."""
    assert i18n._normalize(value) is None


# --- resolution order --------------------------------------------------


def test_env_var_wins(monkeypatch):
    monkeypatch.setenv(i18n.ENV_VAR, "zh")
    assert i18n.resolve_language() == "zh"


def test_env_var_beats_config(monkeypatch, tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"language": "en"}), encoding="utf-8")
    monkeypatch.setattr(i18n, "_from_config", lambda: "en")
    monkeypatch.setenv(i18n.ENV_VAR, "zh")

    assert i18n.resolve_language() == "zh"


def test_config_is_used_when_no_env(monkeypatch):
    monkeypatch.setattr(i18n, "_from_config", lambda: "zh")
    assert i18n.resolve_language() == "zh"


def test_locale_is_used_when_no_env_or_config(monkeypatch):
    monkeypatch.setattr(i18n, "_from_config", lambda: None)
    monkeypatch.setattr(i18n, "_from_locale", lambda: "zh")
    assert i18n.resolve_language() == "zh"


def test_falls_back_to_english(monkeypatch):
    monkeypatch.setattr(i18n, "_from_config", lambda: None)
    monkeypatch.setattr(i18n, "_from_locale", lambda: None)
    assert i18n.resolve_language() == "en"


def test_an_unreadable_config_does_not_raise(monkeypatch, tmp_path):
    bad = tmp_path / "config.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(
        i18n, "get_default_config_path", lambda root: bad, raising=False
    )

    assert i18n._from_config() is None


def test_resolution_is_cached(monkeypatch):
    calls = []

    def counting():
        calls.append(1)
        return "zh"

    monkeypatch.setattr(i18n, "_from_config", counting)
    i18n.resolve_language()
    i18n.resolve_language()

    assert len(calls) == 1


# --- lookup ------------------------------------------------------------


def test_returns_the_active_language(monkeypatch):
    monkeypatch.setenv(i18n.ENV_VAR, "zh")
    assert "资源组" in i18n.t("project.pick_group")

    i18n.set_language("en")
    assert "resource group" in i18n.t("project.pick_group")


def test_interpolates_arguments():
    i18n.set_language("en")
    assert "my-group" in i18n.t("project.registered", group="my-group")


def test_unknown_key_degrades_to_the_key():
    assert i18n.t("no.such.key") == "no.such.key"


def test_missing_translation_falls_back_to_english(monkeypatch):
    monkeypatch.setitem(i18n.MESSAGES, "probe", {"en": "english only"})
    i18n.set_language("zh")

    assert i18n.t("probe") == "english only"


def test_a_bad_placeholder_returns_the_template_rather_than_raising():
    """A message must never crash the command it is reporting on."""
    i18n.set_language("en")
    assert i18n.t("project.registered") == i18n.MESSAGES["project.registered"]["en"]


def test_every_message_is_defined_in_both_languages():
    missing = [
        key
        for key, entry in i18n.MESSAGES.items()
        if not all(lang in entry for lang in i18n.SUPPORTED_LANGUAGES)
    ]
    assert missing == []


def test_placeholders_match_across_languages():
    """A zh string that forgot a placeholder would silently drop information."""
    import re

    fields = lambda s: set(re.findall(r"\{(\w+)\}", s))  # noqa: E731
    mismatched = [
        key
        for key, entry in i18n.MESSAGES.items()
        if fields(entry["en"]) != fields(entry["zh"])
    ]
    assert mismatched == []
