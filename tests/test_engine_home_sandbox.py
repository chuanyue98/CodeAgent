"""测试沙箱清掉的引擎目录变量要覆盖 ca 实际会读的那些。"""

from __future__ import annotations

import os
import re
from pathlib import Path

from tests.conftest import ENGINE_HOME_VARS

ROOT = Path(__file__).resolve().parent.parent
# 引擎目录类变量：*_HOME、*_CONFIG_DIR，以及 ca 自己记的用户 codex home。
_READ = re.compile(r"""environ(?:\.get)?[\(\[]\s*["']([A-Z_]*(?:_HOME|_CONFIG_DIR))["']""")
_NAMED = re.compile(r"""^\s*[A-Z_]+_ENV\s*=\s*["']([A-Z_]*(?:_HOME|_CONFIG_DIR))["']""", re.M)
# 不是引擎目录的：ca 自己的数据目录等。
_NOT_ENGINE = {"CA_HOME", "CODEAGENT_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME"}


def _read_vars() -> set[str]:
    found: set[str] = set()
    for folder in ("core", "engines"):
        for path in (ROOT / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            found.update(_READ.findall(text))
            found.update(_NAMED.findall(text))
    return found - _NOT_ENGINE


def test_sandbox_clears_every_engine_home_variable_ca_reads():
    missing = _read_vars() - set(ENGINE_HOME_VARS)
    assert not missing, f"tests/conftest.py 的 ENGINE_HOME_VARS 漏了：{sorted(missing)}"


def test_engine_home_variables_are_not_inherited():
    for var in ENGINE_HOME_VARS:
        assert var not in os.environ, var
