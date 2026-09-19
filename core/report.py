"""终端报告的共享构件：状态符号、Section/Check 模型与渲染。

``ca doctor`` 与 ``ca status`` 是两种不同的命令——一个回答"环境是否健康"，
一个回答"这套体系正在为我做什么"——但它们的输出语言必须是同一套，否则
用户要在两种排版之间反复适应。这个模块只放两者共用的部分，各自的汇总
行留在各自的命令里。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

import click

# ── Status symbols ────────────────────────────────────────────────────────────

OK = "[OK]"
WARN = "[!] "
FAIL = "[X] "
INFO = "[i] "

STATUS_COLORS = {
    OK: "green",
    WARN: "yellow",
    FAIL: "red",
    INFO: "cyan",
}

# ── Result model ──────────────────────────────────────────────────────────────


@dataclass
class Check:
    status: str  # OK / WARN / FAIL / INFO
    label: str
    detail: str = ""
    fix_hint: str = ""


@dataclass
class Section:
    title: str
    checks: list[Check] = field(default_factory=list)

    def add(
        self, status: str, label: str, detail: str = "", fix_hint: str = ""
    ) -> None:
        self.checks.append(Check(status, label, detail, fix_hint))


def display_width(text: str) -> int:
    """Terminal columns ``text`` occupies, not its character count.

    Section titles are translated, and CJK characters render two columns
    wide -- so a ``len()``-based rule underlines a Chinese heading to barely
    half its width.
    """
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def render_sections(sections: list[Section]) -> tuple[int, int]:
    """Print every section body and return ``(failures, warnings)``.

    Prints only the sections themselves -- no summary line, because the
    summary is command-specific wording. Callers append their own.

    Uses ``click.style``/``click.echo`` so status markers are color-coded in
    a real terminal, while automatically degrading to plain text when output
    isn't a TTY (piped to a file, CI logs, etc.) -- click detects that for us.
    """
    failures = 0
    warnings = 0
    for section in sections:
        click.echo(f"\n  {section.title}")
        click.echo("  " + "─" * display_width(section.title))
        for c in section.checks:
            status = click.style(c.status, fg=STATUS_COLORS.get(c.status), bold=True)
            line = f"  {status}  {c.label}"
            if c.detail:
                line += f"  —  {c.detail}"
            click.echo(line)
            if c.fix_hint and c.status in (WARN, FAIL):
                click.echo(f"         ↳ {c.fix_hint}")
            if c.status == FAIL:
                failures += 1
            elif c.status == WARN:
                warnings += 1
    return failures, warnings
