import datetime as dt
from pathlib import Path

import pytest

from letters.docgen.filenames import InvalidFolderName, build_filename, resolve_folder, safe_component

TODAY = dt.date(2026, 9, 19)


def test_default_pattern():
    name = build_filename("CLINICALS REQUEST-{member_name}-SENT{MMDDYY}.pdf",
                          member_name="JOHN SMITH", policy_id="P1", case_encounter="E1", today=TODAY)
    assert name == "CLINICALS REQUEST-JOHN SMITH-SENT091926.pdf"


def test_all_placeholders_and_missing_extension():
    name = build_filename("{case_encounter}_{policy_id}_{YYYYMMDD}",
                          member_name="x", policy_id="P/1", case_encounter="E:1", today=TODAY)
    assert name == "E1_P1_20260919.pdf"


def test_safe_component_strips_illegal_characters():
    assert safe_component('SMITH, JOHN <jr>?*|"') == "SMITH, JOHN jr"
    assert safe_component("...") == "_"


def test_resolve_folder_joins_nested_names():
    assert resolve_folder(r"\server\claims", "2026/SMITH_JOHN") == Path(r"\server\claims\2026\SMITH_JOHN")
    assert resolve_folder(r"C:\claims", "SMITH_JOHN") == Path(r"C:\claims\SMITH_JOHN")


@pytest.mark.parametrize("bad", ["", "   ", "..", r"..\other", r"a\..\b", r"C:\x", r"\other\share", "/abs", r"\abs"])
def test_resolve_folder_rejects_escapes(bad):
    with pytest.raises(InvalidFolderName):
        resolve_folder(r"C:\claims", bad)


def test_resolve_folder_requires_root():
    with pytest.raises(InvalidFolderName):
        resolve_folder("", "SMITH")
