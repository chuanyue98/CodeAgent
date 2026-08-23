from __future__ import annotations

import pytest

from core.session_history.paths import (
    normalize_project_path,
    strip_extended_length_prefix,
)


@pytest.mark.parametrize(
    "spelling",
    [
        "E:/demo/CodeAgent",
        r"E:\demo\CodeAgent",
        "e:/demo/codeagent/",
        r"\\?\E:\demo\CodeAgent",
        "//?/e:/demo/codeagent",
    ],
)
def test_every_spelling_of_one_directory_canonicalizes_the_same(spelling: str):
    # Each engine writes the working directory its own way; treating them as
    # different projects is what split one workspace across several rows.
    assert normalize_project_path(spelling) == "e:/demo/codeagent"


def test_unc_extended_length_form_resolves_to_the_network_path():
    # `\\?\UNC\server\share` *is* `\\server\share`, so the prefix cannot just
    # be dropped or the two spellings stay unequal.
    assert normalize_project_path(
        r"\\?\UNC\wsl.localhost\Ubuntu\home\cy\app"
    ) == normalize_project_path("//wsl.localhost/Ubuntu/home/cy/app")


def test_distinct_projects_stay_distinct():
    assert normalize_project_path(r"\\?\E:\demo\App") != normalize_project_path(
        "E:/demo/AppOther"
    )


def test_paths_without_a_prefix_are_untouched_beyond_canonicalization():
    assert normalize_project_path("/home/cy/app") == "/home/cy/app"
    assert normalize_project_path("") == ""


def test_strip_keeps_case_for_values_that_are_displayed():
    # claude_parser assigns the stripped path back onto the session it returns,
    # so folding case here would show lowercase paths in the UI.
    assert strip_extended_length_prefix("//?/E:/demo/CodeAgent") == "E:/demo/CodeAgent"
    assert (
        strip_extended_length_prefix("//?/UNC/Server/Share/Proj")
        == "//Server/Share/Proj"
    )
    assert strip_extended_length_prefix("E:/demo/CodeAgent") == "E:/demo/CodeAgent"
