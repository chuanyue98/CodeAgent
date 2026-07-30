"""Tests for the OpenCode shell-hook bridge.

OpenCode has no shell-command hook mechanism — `settings.json` does not exist
as a concept in the opencode 1.18 binary, and its hooks are JS functions
exported by a plugin module. CodeAgent's `before_tool`/`after_tool` commands
are therefore bridged through a generated plugin.

The behavioural tests here execute the generated JS under node so the bridge is
covered as the thing that actually runs, not just as generated text. They skip
when node is unavailable.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from engines.start_opencode import OpenCodeEngine

node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return OpenCodeEngine()


def _hook(name, event, command):
    return {"name": name, "event": event, "command": command}


# --- generation --------------------------------------------------------


def test_no_hooks_writes_no_bridge(engine):
    assert engine.ensure_hooks_bridge([]) is False
    assert not engine._get_hook_bridge_path().exists()


def test_hooks_of_other_events_write_no_bridge(engine):
    assert engine.ensure_hooks_bridge([_hook("h", "on_session_start", "x")]) is False
    assert not engine._get_hook_bridge_path().exists()


def test_bridge_is_written_and_marked_as_generated(engine):
    assert engine.ensure_hooks_bridge([_hook("h", "before_tool", "echo hi")]) is True

    content = engine._get_hook_bridge_path().read_text(encoding="utf-8")
    assert "_ca_injected: true" in content[:500]
    assert "tool.execute.before" in content


def test_bridge_is_removed_when_hooks_are_dropped(engine):
    engine.ensure_hooks_bridge([_hook("h", "before_tool", "echo hi")])
    bridge = engine._get_hook_bridge_path()
    assert bridge.exists()

    engine.ensure_hooks_bridge([])

    assert not bridge.exists()


def test_refuses_to_overwrite_an_unmanaged_file(engine):
    bridge = engine._get_hook_bridge_path()
    bridge.parent.mkdir(parents=True)
    bridge.write_text("// hand-written by the user\n", encoding="utf-8")

    assert engine.ensure_hooks_bridge([_hook("h", "before_tool", "echo hi")]) is False
    assert bridge.read_text(encoding="utf-8") == "// hand-written by the user\n"


def test_removal_leaves_an_unmanaged_file_alone(engine):
    bridge = engine._get_hook_bridge_path()
    bridge.parent.mkdir(parents=True)
    bridge.write_text("// hand-written\n", encoding="utf-8")

    engine.ensure_hooks_bridge([])

    assert bridge.exists()


def test_commands_are_escaped_into_the_js_literal(engine):
    """A quote in a command must not break out of the JS string."""
    engine.ensure_hooks_bridge(
        [_hook('evil"name', "before_tool", 'echo "); process.exit(1); //')]
    )

    content = engine._get_hook_bridge_path().read_text(encoding="utf-8")
    # json.dumps escaping means the raw quote never appears unescaped.
    assert '\\"); process.exit(1); //' in content


def test_cleanup_removes_the_generated_bridge(engine):
    engine.ensure_hooks_bridge([_hook("h", "before_tool", "echo hi")])
    assert engine._get_hook_bridge_path().exists()

    engine.cleanup_plugins_link()

    assert not engine._get_hook_bridge_path().exists()


def test_cleanup_removes_generated_plugin_adapters(engine):
    """Regression: the marker check used to unlink inside its own ``with
    open(...)`` block, which Windows refuses (the handle is still open) and the
    bare ``except`` swallowed — so every generated adapter leaked into the
    user's project."""
    link_dir = engine._get_plugin_link_dir()
    link_dir.mkdir(parents=True)
    generated = link_dir / "ca_adapter_demo.js"
    generated.write_text("// _ca_injected: true\nexport default 1;\n", encoding="utf-8")

    engine.cleanup_plugins_link()

    assert not generated.exists()


def test_cleanup_leaves_unmanaged_files_in_the_plugin_dir_alone(engine):
    link_dir = engine._get_plugin_link_dir()
    link_dir.mkdir(parents=True)
    theirs = link_dir / "ca_adapter_handwritten.js"
    theirs.write_text("export default 1;\n", encoding="utf-8")

    engine.cleanup_plugins_link()

    assert theirs.exists()


# --- behaviour, executed under node -------------------------------------


def _run_bridge(tmp_path, engine, before, after, script):
    """Writes the bridge plus a driver script and runs them under node."""
    engine.ensure_hooks_bridge(before + after)
    bridge = engine._get_hook_bridge_path()

    driver = tmp_path / "driver.mjs"
    bridge_url = bridge.resolve().as_uri()
    driver.write_text(
        f"import bridge from {json.dumps(bridge_url)};\n"
        "const hooks = await bridge();\n" + textwrap.dedent(script),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["node", str(driver)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    return result


@node
def test_before_hook_allows_a_call_when_the_hook_is_silent(tmp_path, engine):
    result = _run_bridge(
        tmp_path,
        engine,
        [_hook("quiet", "before_tool", f'"{sys.executable}" -c "pass"')],
        [],
        """
        await hooks['tool.execute.before'](
          { tool: 'bash', sessionID: 's' }, { args: { command: 'ls' } });
        console.log('ALLOWED');
        """,
    )
    assert "ALLOWED" in result.stdout, result.stderr


@node
def test_before_hook_blocks_on_a_deny_decision(tmp_path, engine):
    denier = (
        f'"{sys.executable}" -c "print(\'{{\\"hookSpecificOutput\\": '
        '{\\"permissionDecision\\": \\"deny\\", '
        '\\"permissionDecisionReason\\": \\"no touching\\"}}\')"'
    )
    result = _run_bridge(
        tmp_path,
        engine,
        [_hook("guard", "before_tool", denier)],
        [],
        """
        try {
          await hooks['tool.execute.before'](
            { tool: 'bash', sessionID: 's' }, { args: {} });
          console.log('ALLOWED');
        } catch (e) { console.log('BLOCKED:' + e.message); }
        """,
    )
    assert "BLOCKED:" in result.stdout, result.stderr
    assert "no touching" in result.stdout
    assert "guard" in result.stdout


@node
def test_before_hook_blocks_on_exit_code_2(tmp_path, engine):
    """Exit code 2 is Claude's block convention, with feedback on stderr."""
    blocker = f'"{sys.executable}" -c "import sys; print(\'why not\', file=sys.stderr); sys.exit(2)"'
    result = _run_bridge(
        tmp_path,
        engine,
        [_hook("two", "before_tool", blocker)],
        [],
        """
        try {
          await hooks['tool.execute.before'](
            { tool: 'bash', sessionID: 's' }, { args: {} });
          console.log('ALLOWED');
        } catch (e) { console.log('BLOCKED:' + e.message); }
        """,
    )
    assert "BLOCKED:" in result.stdout, result.stderr
    assert "why not" in result.stdout


@node
def test_plain_stdout_is_not_mistaken_for_a_denial(tmp_path, engine):
    """Hooks like ci-monitor print progress text; that must not block."""
    noisy = f'"{sys.executable}" -c "print(\'waiting for CI...\')"'
    result = _run_bridge(
        tmp_path,
        engine,
        [_hook("noisy", "before_tool", noisy)],
        [],
        """
        try {
          await hooks['tool.execute.before'](
            { tool: 'bash', sessionID: 's' }, { args: {} });
          console.log('ALLOWED');
        } catch (e) { console.log('BLOCKED:' + e.message); }
        """,
    )
    assert "ALLOWED" in result.stdout, result.stderr


@node
def test_a_hook_that_cannot_start_fails_open(tmp_path, engine):
    result = _run_bridge(
        tmp_path,
        engine,
        [_hook("missing", "before_tool", "this-command-does-not-exist-xyz")],
        [],
        """
        try {
          await hooks['tool.execute.before'](
            { tool: 'bash', sessionID: 's' }, { args: {} });
          console.log('ALLOWED');
        } catch (e) { console.log('BLOCKED:' + e.message); }
        """,
    )
    assert "ALLOWED" in result.stdout, result.stderr


@node
def test_opencode_tool_id_is_normalized_to_the_claude_name(tmp_path, engine):
    """The whole point: an unmodified Claude-shaped hook must match under
    OpenCode, whose shell tool is `bash`, not `Bash`."""
    echoer = (
        f'"{sys.executable}" -c "import json,sys; d=json.load(sys.stdin); '
        "print(json.dumps({'hookSpecificOutput': {'permissionDecision': 'deny', "
        "'permissionDecisionReason': d['tool_name'] + '|' + d['opencode_tool_name']}}))\""
    )
    result = _run_bridge(
        tmp_path,
        engine,
        [_hook("echo", "before_tool", echoer)],
        [],
        """
        try {
          await hooks['tool.execute.before'](
            { tool: 'bash', sessionID: 's' }, { args: { command: 'ls' } });
          console.log('ALLOWED');
        } catch (e) { console.log('SAW:' + e.message); }
        """,
    )
    assert "SAW:" in result.stdout, result.stderr
    assert "Bash|bash" in result.stdout


@node
def test_after_hook_appends_feedback_instead_of_discarding_the_result(tmp_path, engine):
    denier = (
        f'"{sys.executable}" -c "print(\'{{\\"hookSpecificOutput\\": '
        '{\\"permissionDecision\\": \\"deny\\", '
        '\\"permissionDecisionReason\\": \\"lint failed\\"}}\')"'
    )
    result = _run_bridge(
        tmp_path,
        engine,
        [],
        [_hook("linter", "after_tool", denier)],
        """
        const out = { title: 't', output: 'tool result', metadata: {} };
        await hooks['tool.execute.after'](
          { tool: 'bash', sessionID: 's', args: {} }, out);
        console.log(JSON.stringify(out.output));
        """,
    )
    assert "tool result" in result.stdout, result.stderr
    assert "lint failed" in result.stdout
    assert "linter" in result.stdout


@node
def test_before_hook_receives_the_tool_arguments(tmp_path, engine):
    echoer = (
        f'"{sys.executable}" -c "import json,sys; d=json.load(sys.stdin); '
        "print(json.dumps({'hookSpecificOutput': {'permissionDecision': 'deny', "
        "'permissionDecisionReason': d['tool_input']['command']}}))\""
    )
    result = _run_bridge(
        tmp_path,
        engine,
        [_hook("echo", "before_tool", echoer)],
        [],
        """
        try {
          await hooks['tool.execute.before'](
            { tool: 'bash', sessionID: 's' },
            { args: { command: 'git push --force' } });
          console.log('ALLOWED');
        } catch (e) { console.log('SAW:' + e.message); }
        """,
    )
    assert "git push --force" in result.stdout, result.stderr


@node
def test_the_real_branch_protection_hook_blocks_a_commit_on_main(tmp_path, engine):
    """End-to-end against the shipped hook, unmodified."""
    hook_path = (
        Path(__file__).resolve().parent.parent / "hooks/base/branch-protection/hook.py"
    )
    # The hook reads the branch via `git rev-parse --abbrev-ref HEAD`, which
    # fails on an unborn branch — so the repo needs one real commit.
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=tmp_path, check=True)
    subprocess.run([*git, "commit", "-qm", "init"], cwd=tmp_path, check=True)

    result = _run_bridge(
        tmp_path,
        engine,
        [
            _hook(
                "branch-protection", "before_tool", f'"{sys.executable}" "{hook_path}"'
            )
        ],
        [],
        """
        try {
          await hooks['tool.execute.before'](
            { tool: 'bash', sessionID: 's' },
            { args: { command: 'git commit -m x' } });
          console.log('ALLOWED');
        } catch (e) { console.log('BLOCKED'); }
        """,
    )
    assert "BLOCKED" in result.stdout, f"{result.stdout}\n{result.stderr}"
