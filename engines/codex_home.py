"""委派时给 codex 一个归 ca 所有的 ``CODEX_HOME``，不往用户的 ``~/.codex`` 里写。

交互式的 ``ca codex`` 仍然把插件登记进用户级 ``~/.codex/config.toml``（见
:mod:`engines.codex_plugins` 与 :mod:`core.injection_ledger`），因为人坐在那里，
要的就是自己那套配置。后台委派没人看着，它只需要借用户的登录，不需要、
也不该改用户的文件。所以委派时 codex 跑在
``~/.codeagent/engine-homes/codex/<资源组>/`` 里，那里的 ``config.toml`` 是 ca
每次启动时重新生成的，收回这一步就不存在了。

从用户那边带过来的只有这些：

- ``auth.json``：硬链接。Windows 上没有开发者模式建不了符号链接，硬链接
  不需要特权，而且读到的就是同一个文件。
- ``sessions/``：链接到用户的 ``sessions/``；``sqlite_home`` 指向用户的 codex
  home。会话历史（扫 rollout 文件）和用量统计（读 ``state_5.sqlite``）照常
  看得到委派跑出来的会话，跟没隔离时一样。
- :data:`CARRIED_KEYS` 里与模型、provider、登录方式有关的配置键，接 relay
  或自建 endpoint 的用户不至于在委派里连不上。

用户的 MCP 服务器、插件、钩子、``notify``、全局 ``AGENTS.md`` 和 ``skills/``
都不带。

硬链接的代价：codex-cli 0.167.0 刷新凭据时做原子替换，二进制里能看到
"atomic credential replacement does not support hard-linked files"，也就是
隔离 home 里的 codex 刷不了 token。所以只在 token 离刷新还远时才隔离
（:func:`credential_refresh_due`），否则这一次退回旧的注入方式。用户自己的
codex 刷新之后，``~/.codex/auth.json`` 换成了新文件，下次启动时重新链接。

以上在 codex-cli 0.167.0（Windows 11）上实测过：硬链接的 auth.json 能正常
登录，跑完仍是同一个文件；``sqlite_home`` 让各个 sqlite 库落在指定目录；
rollout 经联接写进了目标 ``sessions/``。
"""

from __future__ import annotations

import base64
import json
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.link_manager import LinkManager, is_windows_link
from core.lock_manager import LockManager
from core.logging_config import get_logger

logger = get_logger(__name__)

#: 从用户级 ``config.toml`` 带进隔离 home 的键：只有模型、provider 和登录方式。
CARRIED_KEYS = (
    "model",
    "model_provider",
    "model_providers",
    "model_reasoning_effort",
    "model_reasoning_summary",
    "model_verbosity",
    "model_context_window",
    "model_auto_compact_token_limit",
    "model_catalog_json",
    "openai_base_url",
    "chatgpt_base_url",
    "service_tier",
    "forced_login_method",
    "forced_chatgpt_workspace_id",
    "profile",
    "profiles",
)

#: codex 在 ``last_refresh`` 满 8 天后主动刷新 token；留一天余量。
REFRESH_AGE_LIMIT = timedelta(days=7)
#: access token 剩余有效期至少要盖过一次委派（默认超时 30 分钟）。
ACCESS_TOKEN_MIN_REMAINING = timedelta(hours=12)


#: 隔离运行时，子进程的 ``CODEX_HOME`` 指向隔离 home，用户真正的 home 记在
#: 这里。隔离的 codex 里再发起委派时，下一层据此找回用户的 home，而不是把
#: 隔离 home 当成用户的。
USER_HOME_ENV = "CA_USER_CODEX_HOME"


class IsolatedHomeUnavailable(Exception):
    """这一次没法隔离；消息是给用户看的原因。"""


def user_codex_home() -> Path:
    """用户自己的 codex home。

    依次取 :data:`USER_HOME_ENV`（上一层隔离运行留下的）、``CODEX_HOME``、
    ``~/.codex``。
    """
    configured = os.environ.get(USER_HOME_ENV) or os.environ.get("CODEX_HOME")
    return Path(configured) if configured else Path.home() / ".codex"


def child_codex_env(env: dict[str, str], isolated_home: Path | None) -> None:
    """按本次是否隔离，设好子进程 codex 该用的 ``CODEX_HOME``。"""
    user_home = user_codex_home()
    if isolated_home is not None:
        env["CODEX_HOME"] = str(isolated_home)
        env[USER_HOME_ENV] = str(user_home)
    elif USER_HOME_ENV in env:
        # 上一层是隔离运行，继承来的 CODEX_HOME 是它的隔离 home；这一层没有
        # 隔离，就该回到用户自己的 home。
        env["CODEX_HOME"] = str(user_home)
        del env[USER_HOME_ENV]


def isolated_codex_home(group: str) -> Path:
    """资源组 *group* 的隔离 home。不同资源组挂的插件不同，各用一个。"""
    safe = re.sub(r"[^\w.-]", "_", group) or "common"
    return Path.home() / ".codeagent" / "engine-homes" / "codex" / safe


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    # codex 写的是纳秒精度（2026-11-05T09:05:57.128604500Z），fromisoformat
    # 只吃到微秒，多出的位数截掉。
    text = re.sub(r"(\.\d{6})\d+", r"\1", value.replace("Z", "+00:00"))
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _jwt_expiry(token: Any) -> datetime | None:
    if not isinstance(token, str) or token.count(".") < 2:
        return None
    payload = token.split(".")[1]
    try:
        claims = json.loads(
            base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        )
        return datetime.fromtimestamp(int(claims["exp"]), tz=UTC)
    except (ValueError, KeyError, TypeError):
        return None


def credential_refresh_due(
    auth: dict[str, Any], now: datetime | None = None
) -> str | None:
    """codex 在这次委派里可能要刷新 token 时返回原因，否则 ``None``。

    API key 登录没有 token 可刷，永远不到期。判断不了（字段缺失、格式不认识）
    就当作要刷新：宁可这一次不隔离，也别让刷新撞上硬链接。
    """
    tokens = auth.get("tokens")
    if not isinstance(tokens, dict) or not tokens.get("refresh_token"):
        return None
    now = now or datetime.now(UTC)
    last_refresh = _parse_time(auth.get("last_refresh"))
    if last_refresh is None:
        return "auth.json 里没有可读的 last_refresh"
    if now - last_refresh >= REFRESH_AGE_LIMIT:
        return f"token 上次刷新于 {last_refresh:%Y-%m-%d}，codex 快要刷新它了"
    expiry = _jwt_expiry(tokens.get("access_token"))
    if expiry is None:
        return "读不出 access token 的有效期"
    if expiry - now < ACCESS_TOKEN_MIN_REMAINING:
        return f"access token 将于 {expiry:%Y-%m-%d %H:%M} 过期"
    return None


def _link_credential(source: Path, target: Path) -> None:
    """让 *target* 成为 *source* 的硬链接；已经是就不动。"""
    if os.path.lexists(target):
        try:
            if os.path.samefile(source, target):
                return
        except OSError:
            pass
        # 用户的 codex 刷新过 token，原文件被换掉了，这里是旧的那份。
        target.unlink(missing_ok=True)
    try:
        os.link(source, target)
    except OSError as exc:
        raise IsolatedHomeUnavailable(f"无法硬链接 {source}：{exc}") from exc


def _link_sessions(home: Path, user_home: Path, links: LinkManager) -> None:
    source = user_home / "sessions"
    source.mkdir(parents=True, exist_ok=True)
    target = home / "sessions"
    if is_windows_link(target):
        try:
            if target.resolve() == source.resolve():
                return
        except OSError:
            pass
        links.safe_remove_link(target)
    elif os.path.lexists(target):
        raise IsolatedHomeUnavailable(
            f"{target} 是个真实目录而不是链接，委派的会话会看不到；删掉它后再试"
        )
    try:
        links.create_skill_link(source, target)
    except Exception as exc:
        raise IsolatedHomeUnavailable(f"无法链接 {target} → {source}：{exc}") from exc


def _project_key(path: Path) -> str:
    return str(path.resolve())


def build_config(
    user_config: Any,
    previous_config: Any,
    user_home: Path,
    cwd: Path,
    format_plugins: Callable[[Any], Any],
) -> Any:
    """生成隔离 home 的 ``config.toml``。

    Args:
        user_config: 用户级 ``config.toml`` 的解析结果（tomlkit 文档）。
        previous_config: 隔离 home 里上一份 ``config.toml``，用来保留并发委派
            登记的项目信任；没有就传空文档。
        user_home: 用户的 codex home，``sqlite_home`` 指向它。
        cwd: 本次委派的工作目录，标为受信任，项目里注入的钩子才会被加载。
        format_plugins: 把本资源组的插件写进文档的函数。
    """
    import tomlkit

    doc = tomlkit.document()
    doc.add(tomlkit.comment("由 CodeAgent 为委派生成，每次启动都会重写，不要手改。"))
    for key in CARRIED_KEYS:
        if key in user_config:
            value = user_config[key]
            doc[key] = value.unwrap() if hasattr(value, "unwrap") else value
    # 只在 auth.json 存在时才隔离；"auto" 可能去查按 home 区分的 keyring，查不到。
    doc["cli_auth_credentials_store"] = "file"
    doc["sqlite_home"] = user_home.resolve().as_posix()

    projects = tomlkit.table()
    previous = previous_config.get("projects", {}) if previous_config else {}
    for key, entry in previous.items():
        # 委派用完的 worktree 会被删掉，它们的信任条目没必要留着。
        if Path(key).exists():
            projects[key] = entry.unwrap() if hasattr(entry, "unwrap") else entry
    projects[_project_key(cwd)] = {"trust_level": "trusted"}
    doc["projects"] = projects

    return format_plugins(doc)


def prepare_isolated_codex_home(
    group: str,
    cwd: Path,
    load_config: Callable[[Path], Any],
    save_config: Callable[[Path, Any], None],
    format_plugins: Callable[[Any], Any],
    *,
    home: Path | None = None,
    user_home: Path | None = None,
    lock_manager: LockManager | None = None,
) -> Path:
    """准备好隔离 home 并返回它；做不到时抛 :class:`IsolatedHomeUnavailable`。

    整个准备过程在 home 的锁里做：同一资源组的委派可能同时启动，链接和
    配置文件不能互相踩。锁只包准备这一步，codex 运行期间不持有。
    """
    user_home = user_home or user_codex_home()
    home = home or isolated_codex_home(group)

    user_config = load_config(user_home / "config.toml")
    if user_config is None:
        raise IsolatedHomeUnavailable(f"{user_home / 'config.toml'} 读不懂")
    store = user_config.get("cli_auth_credentials_store")
    if store == "keyring":
        raise IsolatedHomeUnavailable(
            "codex 的凭据存在系统 keyring 里，没有可共享的 auth.json"
        )

    auth_path = user_home / "auth.json"
    try:
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise IsolatedHomeUnavailable(
            f"{auth_path} 不存在（codex 还没登录？）"
        ) from exc
    except (OSError, ValueError) as exc:
        raise IsolatedHomeUnavailable(f"{auth_path} 读不懂：{exc}") from exc
    if not isinstance(auth, dict):
        raise IsolatedHomeUnavailable(f"{auth_path} 格式不认识")
    due = credential_refresh_due(auth)
    if due:
        raise IsolatedHomeUnavailable(
            f"{due}；隔离 home 里的 codex 刷新不了硬链接的凭据"
        )

    home.mkdir(parents=True, exist_ok=True)
    locks = lock_manager or LockManager()
    handle = locks.acquire_resource_lock(home / ".prepare.lock")
    try:
        _link_credential(auth_path, home / "auth.json")
        _link_sessions(home, user_home, LinkManager())
        config_path = home / "config.toml"
        previous = load_config(config_path)
        config = build_config(user_config, previous, user_home, cwd, format_plugins)
        save_config(config_path, config)
    finally:
        locks.release_resource_lock(handle)
    return home


__all__ = [
    "CARRIED_KEYS",
    "IsolatedHomeUnavailable",
    "USER_HOME_ENV",
    "build_config",
    "child_codex_env",
    "credential_refresh_due",
    "isolated_codex_home",
    "prepare_isolated_codex_home",
    "user_codex_home",
]
