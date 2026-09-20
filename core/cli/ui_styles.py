"""Shared UI styles, engine color themes, and Questionary token formatters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import questionary
from questionary import Style

from core.constants import normalize_engine_name
from core.i18n import t
from core.report import display_width


@dataclass(frozen=True)
class EngineTheme:
    """Color theme and visual badge specification for an AI engine."""

    name: str
    display_name: str
    badge: str
    hex_color: str
    rgb_color: tuple[int, int, int]
    click_fg: str | tuple[int, int, int]
    style_class: str


ENGINE_THEMES: dict[str, EngineTheme] = {
    "claude": EngineTheme(
        name="claude",
        display_name="Claude",
        badge="[Claude]",
        hex_color="#f97316",
        rgb_color=(249, 115, 22),
        click_fg=(249, 115, 22),
        style_class="eng_claude",
    ),
    "codex": EngineTheme(
        name="codex",
        display_name="Codex",
        badge="[Codex]",
        hex_color="#10b981",
        rgb_color=(16, 185, 129),
        click_fg=(16, 185, 129),
        style_class="eng_codex",
    ),
    "opencode": EngineTheme(
        name="opencode",
        display_name="OpenCode",
        badge="[OpenCode]",
        hex_color="#3b82f6",
        rgb_color=(59, 130, 246),
        click_fg=(59, 130, 246),
        style_class="eng_opencode",
    ),
    "antigravity": EngineTheme(
        name="antigravity",
        display_name="Antigravity",
        badge="[Antigravity]",
        hex_color="#a855f7",
        rgb_color=(168, 85, 247),
        click_fg=(168, 85, 247),
        style_class="eng_antigravity",
    ),
    "codebuddy": EngineTheme(
        name="codebuddy",
        display_name="CodeBuddy",
        badge="[CodeBuddy]",
        hex_color="#06b6d4",
        rgb_color=(6, 182, 212),
        click_fg=(6, 182, 212),
        style_class="eng_codebuddy",
    ),
}

DEFAULT_ENGINE_THEME = EngineTheme(
    name="unknown",
    display_name="Other",
    badge="[Other]",
    hex_color="#94a3b8",
    rgb_color=(148, 163, 184),
    click_fg="bright_white",
    style_class="eng_other",
)


def get_engine_theme(engine: str | None) -> EngineTheme:
    """Returns the EngineTheme corresponding to the given engine name."""
    if not engine:
        return DEFAULT_ENGINE_THEME
    try:
        norm = normalize_engine_name(engine)
    except Exception:
        norm = engine.strip().lower()

    if norm in ENGINE_THEMES:
        return ENGINE_THEMES[norm]

    badge = f"[{norm.capitalize()}]"
    return EngineTheme(
        name=norm,
        display_name=norm.capitalize(),
        badge=badge,
        hex_color="#94a3b8",
        rgb_color=(148, 163, 184),
        click_fg="bright_white",
        style_class="eng_other",
    )


class StyledTitle(list[tuple[str, str]]):
    """List of (style_class, text) tuples with string fallback methods for questionary.

    Behaves as a list so Questionary's internal token generator accepts it,
    while implementing .lower() and .__str__() so Questionary's search filter
    and string formatting continue to work without errors.
    """

    def __init__(self, tokens: list[tuple[str, str]], plain: str) -> None:
        super().__init__(tokens)
        self.plain = plain

    def lower(self) -> str:
        return self.plain.lower()

    def __str__(self) -> str:
        return self.plain

    def __repr__(self) -> str:
        return f"StyledTitle({self.plain!r})"


CLI_QUESTIONARY_STYLE: Style = questionary.Style(
    [
        ("qmark", "fg:#3b82f6 bold"),
        ("question", "bold"),
        ("pointer", "fg:#3b82f6 bold"),
        ("highlighted", "fg:#60a5fa bold"),
        ("selected", "fg:#10b981"),
        ("separator", "fg:#64748b"),
        ("instruction", "fg:#94a3b8"),
        # Engine brand colors
        ("eng_claude", "fg:#f97316 bold"),
        ("eng_codex", "fg:#10b981 bold"),
        ("eng_opencode", "fg:#3b82f6 bold"),
        ("eng_antigravity", "fg:#a855f7 bold"),
        ("eng_codebuddy", "fg:#06b6d4 bold"),
        ("eng_other", "fg:#94a3b8 bold"),
        # Status indicators
        ("badge_ready", "fg:#10b981 bold"),
        ("badge_missing", "fg:#64748b"),
        # Session row elements
        ("idx", "fg:#64748b"),
        ("time", "fg:#94a3b8"),
        ("dim", "fg:#64748b"),
        ("pipe", "fg:#475569"),
        ("session_title", "fg:#f8fafc"),
    ]
)


def pad_display(text: str, width: int) -> str:
    """Pads string to exact terminal column width, accounting for wide CJK characters."""
    w = display_width(text)
    if w < width:
        return text + " " * (width - w)
    return text


def format_styled_session_choice(
    idx: int, s: dict[str, Any], relative_time_str: str
) -> StyledTitle:
    """Formats a session row into a StyledTitle token list with engine brand colors."""
    eng_raw = s.get("engine", "unknown")
    theme = get_engine_theme(eng_raw)
    eng_padded = pad_display(theme.badge, 14)
    time_padded = pad_display(relative_time_str, 12)

    msg_count = s.get("message_count", 0)
    msg_str = f"{msg_count:3d} msgs"

    title = s.get("title") or t("history.no_title")
    title = title.replace("\n", " ").strip()
    if len(title) > 50:
        title = title[:47] + "..."

    tokens = [
        ("class:idx", f"[{idx:2d}]  "),
        (f"class:{theme.style_class}", eng_padded),
        ("class:time", f" {time_padded}"),
        ("class:dim", f" · {msg_str}  "),
        ("class:pipe", "│ "),
        ("class:session_title", title),
    ]
    plain = f"[{idx:2d}]  {eng_padded} {time_padded} · {msg_str}  │ {title}"
    return StyledTitle(tokens, plain)
