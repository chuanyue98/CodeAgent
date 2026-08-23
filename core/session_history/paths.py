"""Canonical form for the project paths recorded in session history.

Every engine writes the working directory into its own history in its own
spelling, and the same directory legitimately shows up several ways:

    E:/demo/CodeAgent            (opencode)
    E:\\demo\\CodeAgent            (claude)
    \\\\?\\E:\\demo\\CodeAgent         (codex, Windows extended-length form)
    \\\\?\\UNC\\server\\share\\proj    (codex, UNC under the same form)

Comparing those as plain strings splits one workspace into several, which is
how filtering Sessions by a workspace ended up hiding the codex runs for that
very directory. One helper, used by every parser and by the analytics router,
so the whole app agrees on what "the same project" means.
"""

from __future__ import annotations

# Windows extended-length prefixes. `\\?\UNC\server\share` denotes the network
# path `\\server\share`, so that one is rewritten rather than merely dropped.
_EXTENDED_UNC_PREFIX = "//?/unc/"
_EXTENDED_PREFIX = "//?/"


def strip_extended_length_prefix(path: str) -> str:
    """Removes a Windows extended-length prefix, leaving case untouched.

    For callers that compare paths but also display or store the result, so
    folding case would leak into the UI. Expects forward slashes already.
    """
    lowered = path.lower()
    if lowered.startswith(_EXTENDED_UNC_PREFIX):
        return "//" + path[len(_EXTENDED_UNC_PREFIX) :]
    if lowered.startswith(_EXTENDED_PREFIX):
        return path[len(_EXTENDED_PREFIX) :]
    return path


def normalize_project_path(path: str) -> str:
    """Canonicalizes a project path for equality comparison.

    Separators unified, case folded, trailing separator dropped, and Windows
    extended-length prefixes resolved — so a workspace registered as
    ``E:\\demo\\App`` matches session records written as ``e:/demo/app/`` or
    ``\\\\?\\E:\\demo\\App``.

    Comparison only: the result is not a path to hand back to the filesystem or
    show to anyone. Use :func:`strip_extended_length_prefix` when the value is
    also displayed or stored.
    """
    return strip_extended_length_prefix(path.replace("\\", "/").lower()).rstrip("/")
