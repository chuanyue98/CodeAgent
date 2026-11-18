"""委派时的 codex 隔离 home（engines/codex_home.py）。

硬链接凭据、``sqlite_home``、sessions 联接的行为在 codex-cli 0.167.0 上实测过，
见模块说明；这里只测 ca 自己这一侧：链了什么、写了什么、什么时候退回。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import tomlkit

from engines.codex_home import (
    USER_HOME_ENV,
    IsolatedHomeUnavailable,
    build_config,
    child_codex_env,
    credential_refresh_due,
    prepare_isolated_codex_home,
    user_codex_home,
)

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def _jwt(exp: datetime) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": int(exp.timestamp())}).encode()
    ).rstrip(b"=")
    return f"h.{payload.decode()}.s"


def _chatgpt_auth(last_refresh: datetime, access_exp: datetime) -> dict:
    return {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": None,
        "tokens": {
            "access_token": _jwt(access_exp),
            "refresh_token": "r",
            "id_token": "i",
        },
        # codex 写的是纳秒精度。
        "last_refresh": last_refresh.strftime("%Y-%m-%dT%H:%M:%S.123456789Z"),
    }


def _load(path: Path):
    if not path.exists():
        return tomlkit.parse("")
    try:
        return tomlkit.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save(path: Path, data) -> None:
    path.write_text(tomlkit.dumps(data), encoding="utf-8")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(autouse=True)
def _no_inherited_codex_home(monkeypatch):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv(USER_HOME_ENV, raising=False)


@pytest.fixture
def user_home(tmp_path):
    home = tmp_path / "user-codex"
    home.mkdir()
    (home / "config.toml").write_text(
        'model = "gpt-6.1-sol"\n'
        'model_reasoning_effort = "max"\n'
        'notify = ["notifier.exe"]\n'
        "[mcp_servers.node_repl]\n"
        'command = "node"\n'
        "[model_providers.relay]\n"
        'base_url = "https://relay.example/v1"\n'
        '[projects."C:\\\\elsewhere"]\n'
        'trust_level = "trusted"\n',
        encoding="utf-8",
    )
    fresh = datetime.now(UTC) - timedelta(days=1)
    (home / "auth.json").write_text(
        json.dumps(_chatgpt_auth(fresh, fresh + timedelta(days=10))), encoding="utf-8"
    )
    return home


def _prepare(tmp_path, user_home, cwd=None, format_plugins=lambda doc: doc):
    return prepare_isolated_codex_home(
        "common",
        cwd or tmp_path,
        _load,
        _save,
        format_plugins,
        home=tmp_path / "iso",
        user_home=user_home,
    )


# ── 什么时候 token 会刷新 ──────────────────────────────────────────────────


def test_api_key_login_never_needs_a_refresh():
    assert (
        credential_refresh_due({"auth_mode": "apikey", "OPENAI_API_KEY": "k"}) is None
    )


def test_recently_refreshed_token_is_safe_to_share():
    auth = _chatgpt_auth(NOW - timedelta(days=4), NOW + timedelta(days=6))
    assert credential_refresh_due(auth, NOW) is None


def test_token_close_to_codex_refresh_age_is_not_shared():
    auth = _chatgpt_auth(NOW - timedelta(days=7, hours=1), NOW + timedelta(days=3))
    assert "快要刷新" in credential_refresh_due(auth, NOW)


def test_access_token_about_to_expire_is_not_shared():
    auth = _chatgpt_auth(NOW - timedelta(days=1), NOW + timedelta(hours=2))
    assert "过期" in credential_refresh_due(auth, NOW)


def test_unreadable_refresh_time_counts_as_due():
    auth = _chatgpt_auth(NOW, NOW + timedelta(days=9))
    auth["last_refresh"] = "yesterday-ish"
    assert credential_refresh_due(auth, NOW) is not None


# ── 生成的配置 ──────────────────────────────────────────────────────────


def test_config_carries_model_settings_but_not_personal_setup(tmp_path, user_home):
    doc = build_config(
        _load(user_home / "config.toml"),
        tomlkit.parse(""),
        user_home,
        tmp_path,
        lambda d: d,
    )
    assert doc["model"] == "gpt-6.1-sol"
    assert doc["model_reasoning_effort"] == "max"
    assert doc["model_providers"]["relay"]["base_url"] == "https://relay.example/v1"
    for personal in ("notify", "mcp_servers"):
        assert personal not in doc
    assert doc["sqlite_home"] == user_home.resolve().as_posix()
    assert doc["cli_auth_credentials_store"] == "file"
    # 用户自己信任的项目不带过来，只信任本次委派的目录。
    assert list(doc["projects"]) == [str(tmp_path.resolve())]
    assert doc["projects"][str(tmp_path.resolve())]["trust_level"] == "trusted"


def test_concurrent_delegations_keep_each_others_trust(tmp_path, user_home):
    """并发委派的目录还在就留着它的信任，删掉的 worktree 就丢掉。"""
    other = tmp_path / "other-worktree"
    other.mkdir()
    previous = tomlkit.parse("")
    previous["projects"] = {
        str(other.resolve()): {"trust_level": "trusted"},
        str(tmp_path / "gone"): {"trust_level": "trusted"},
    }
    doc = build_config(
        _load(user_home / "config.toml"), previous, user_home, tmp_path, lambda d: d
    )
    assert set(doc["projects"]) == {str(other.resolve()), str(tmp_path.resolve())}


# ── 准备隔离 home ────────────────────────────────────────────────────────


def test_prepare_links_credentials_and_sessions_without_touching_user_files(
    tmp_path, user_home
):
    before = _digest(user_home / "config.toml")
    home = _prepare(tmp_path, user_home)

    assert os.path.samefile(home / "auth.json", user_home / "auth.json")
    assert (home / "sessions").resolve() == (user_home / "sessions").resolve()
    assert _load(home / "config.toml")["model"] == "gpt-6.1-sol"
    assert _digest(user_home / "config.toml") == before
    assert sorted(p.name for p in user_home.iterdir()) == [
        "auth.json",
        "config.toml",
        "sessions",
    ]


def test_prepare_twice_is_idempotent(tmp_path, user_home):
    first = _prepare(tmp_path, user_home)
    config = (first / "config.toml").read_text(encoding="utf-8")
    second = _prepare(tmp_path, user_home)
    assert second == first
    assert os.path.samefile(second / "auth.json", user_home / "auth.json")
    assert (second / "config.toml").read_text(encoding="utf-8") == config


def test_relinks_after_users_codex_replaced_auth_json(tmp_path, user_home):
    """用户的 codex 刷新 token 时会原子替换 auth.json，旧链接就成了旧文件。"""
    home = _prepare(tmp_path, user_home)
    replacement = user_home / "auth.json.new"
    replacement.write_text((user_home / "auth.json").read_text(), encoding="utf-8")
    os.replace(replacement, user_home / "auth.json")
    assert not os.path.samefile(home / "auth.json", user_home / "auth.json")

    _prepare(tmp_path, user_home)
    assert os.path.samefile(home / "auth.json", user_home / "auth.json")


def test_plugins_are_written_into_the_isolated_config(tmp_path, user_home):
    def add_plugin(doc):
        doc["plugins"] = {"demo@codeagent-local": {"enabled": True}}
        return doc

    home = _prepare(tmp_path, user_home, format_plugins=add_plugin)
    assert _load(home / "config.toml")["plugins"]["demo@codeagent-local"]["enabled"]
    assert "plugins" not in _load(user_home / "config.toml")


@pytest.mark.parametrize(
    "breakage, reason",
    [
        (lambda h: (h / "auth.json").unlink(), "不存在"),
        (lambda h: (h / "auth.json").write_text("{", encoding="utf-8"), "读不懂"),
        (
            lambda h: (h / "config.toml").write_text("= nope", encoding="utf-8"),
            "读不懂",
        ),
        (
            lambda h: (h / "config.toml").write_text(
                'cli_auth_credentials_store = "keyring"\n', encoding="utf-8"
            ),
            "keyring",
        ),
        (
            lambda h: (h / "auth.json").write_text(
                json.dumps(
                    _chatgpt_auth(
                        datetime.now(UTC) - timedelta(days=9),
                        datetime.now(UTC) + timedelta(days=1),
                    )
                ),
                encoding="utf-8",
            ),
            "快要刷新",
        ),
    ],
)
def test_prepare_refuses_and_says_why(tmp_path, user_home, breakage, reason):
    breakage(user_home)
    with pytest.raises(IsolatedHomeUnavailable, match=reason):
        _prepare(tmp_path, user_home)
    assert not (tmp_path / "iso" / "auth.json").exists()


# ── 子进程的 CODEX_HOME ─────────────────────────────────────────────────


def test_isolated_child_gets_isolated_home_and_remembers_the_users(tmp_path):
    env: dict[str, str] = {}
    child_codex_env(env, tmp_path / "iso")
    assert env["CODEX_HOME"] == str(tmp_path / "iso")
    assert env[USER_HOME_ENV] == str(Path.home() / ".codex")


def test_nested_delegation_finds_the_real_user_home(tmp_path, monkeypatch):
    """隔离的 codex 再发起委派时，继承来的 CODEX_HOME 是隔离 home。"""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "iso"))
    monkeypatch.setenv(USER_HOME_ENV, str(tmp_path / "real"))
    assert user_codex_home() == tmp_path / "real"

    env = {"CODEX_HOME": str(tmp_path / "iso"), USER_HOME_ENV: str(tmp_path / "real")}
    child_codex_env(env, None)
    assert env == {"CODEX_HOME": str(tmp_path / "real")}


def test_interactive_launch_leaves_codex_home_alone():
    env = {"PATH": "x"}
    child_codex_env(env, None)
    assert env == {"PATH": "x"}


# ── 引擎接线 ────────────────────────────────────────────────────────────


def test_engine_falls_back_to_user_home_when_isolation_is_unavailable(
    tmp_path, monkeypatch
):
    from engines.start_codex import CodexEngine

    user = tmp_path / "user-codex"
    user.mkdir()  # 没有 auth.json
    monkeypatch.setenv("CODEX_HOME", str(user))
    monkeypatch.chdir(tmp_path)
    engine = CodexEngine()
    assert engine.use_isolated_home() is None
    assert engine._get_codex_home() == user.resolve()


def test_engine_puts_plugins_under_the_isolated_home(tmp_path, monkeypatch, user_home):
    from engines.start_codex import CodexEngine

    monkeypatch.setenv("CODEX_HOME", str(user_home))
    monkeypatch.setenv("CA_PROJECT_GROUP", "demo-group")
    monkeypatch.chdir(tmp_path)
    plugin_src = tmp_path / "plugin-src"
    plugin_src.mkdir()
    engine = CodexEngine()
    monkeypatch.setattr(
        engine,
        "get_plugins_to_mount",
        lambda: [{"name": "demo", "_plugin_dir": str(plugin_src)}],
    )

    home = engine.use_isolated_home()
    assert home is not None
    assert home.name == "demo-group"
    assert engine._get_plugin_link_dir() == (home / "plugins").resolve()
    config = _load(home / "config.toml")
    assert config["plugins"]["demo@codeagent-local"]["enabled"] is True
    assert "marketplaces" not in _load(user_home / "config.toml")
