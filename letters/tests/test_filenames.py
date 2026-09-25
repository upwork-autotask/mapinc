import datetime as dt
from pathlib import Path

import pytest

from letters.docgen.filenames import (ALLOWED_PLACEHOLDERS, InvalidFilenamePattern, InvalidFolderName,
                                      build_filename, resolve_folder, safe_component, unknown_placeholders)

TODAY = dt.date(2026, 9, 19)


CLIENT_PATTERN = ("{case_encounter}-{case_location}-{case_type}-CLINICALS REQUEST-"
                  "{member_name}-SENT{MMDDYY}-{user}.pdf")


def test_default_pattern():
    name = build_filename("CLINICALS REQUEST-{member_name}-SENT{MMDDYY}.pdf",
                          member_name="JOHN SMITH", policy_id="P1", case_encounter="E1", today=TODAY)
    assert name == "CLINICALS REQUEST-JOHN SMITH-SENT091926.pdf"


def test_client_pattern_with_case_location_type_and_user():
    name = build_filename(CLIENT_PATTERN, member_name="JOHN SMITH", policy_id="P1", case_encounter="E-100",
                          case_location="MIAMI", case_type="INPATIENT", user="DOMAIN\\rabdallah", today=TODAY)
    assert name == "E-100-MIAMI-INPATIENT-CLINICALS REQUEST-JOHN SMITH-SENT091926-rabdallah.pdf"


def test_missing_optional_values_do_not_leave_stray_separators():
    name = build_filename(CLIENT_PATTERN, member_name="JOHN SMITH", policy_id="P1", case_encounter="E-100",
                          today=TODAY)
    assert name == "E-100-CLINICALS REQUEST-JOHN SMITH-SENT091926.pdf"


def test_all_placeholders_and_missing_extension():
    name = build_filename("{case_encounter}_{policy_id}_{YYYYMMDD}",
                          member_name="x", policy_id="P/1", case_encounter="E:1", today=TODAY)
    assert name == "E1_P1_20260919.pdf"


def test_safe_component_strips_illegal_characters():
    assert safe_component('SMITH, JOHN <jr>?*|"') == "SMITH, JOHN jr"
    assert safe_component("...") == "_"


# --- resolve_folder now takes the whole destination path ----------------------

def test_accepts_a_drive_path():
    assert resolve_folder(r"D:\claims\SMITH_JOHN") == Path(r"D:\claims\SMITH_JOHN")


def test_accepts_a_unc_path():
    assert resolve_folder(r"\\server\claims\2026\SMITH_JOHN") == Path(r"\\server\claims\2026\SMITH_JOHN")


def test_accepts_forward_slashes_quotes_and_trailing_separator():
    assert resolve_folder('  "D:/claims/SMITH_JOHN/"  ') == Path(r"D:\claims\SMITH_JOHN")


@pytest.mark.parametrize("bad", ["", "   ", "SMITH_JOHN", r"claims\SMITH", r"\claims\SMITH",
                                 r"D:\claims\..\windows", r"\\server", "/mnt/claims"])
def test_rejects_anything_that_is_not_a_full_windows_path(bad):
    with pytest.raises(InvalidFolderName):
        resolve_folder(bad)


def test_allowed_roots_restrict_where_letters_may_be_written(settings):
    settings.MAPINC_ALLOWED_FOLDER_ROOTS = [r"D:\claims", r"\\server\claims"]
    assert resolve_folder(r"D:\claims\SMITH") == Path(r"D:\claims\SMITH")
    assert resolve_folder(r"\\SERVER\Claims\Smith") == Path(r"\\SERVER\Claims\Smith")  # case-insensitive
    with pytest.raises(InvalidFolderName, match="not an allowed"):
        resolve_folder(r"D:\other\SMITH")


def test_no_allowed_roots_means_any_full_path(settings):
    settings.MAPINC_ALLOWED_FOLDER_ROOTS = []
    assert resolve_folder(r"E:\anywhere") == Path(r"E:\anywhere")


# --- a pattern with a placeholder we do not supply must not crash ------------

def test_unknown_placeholder_is_reported_not_raised_as_keyerror():
    with pytest.raises(InvalidFilenamePattern) as err:
        build_filename("{map_id}-{member_name}.pdf", member_name="A", policy_id="P",
                       case_encounter="E", today=TODAY)
    assert "map_id" in str(err.value)
    assert "{case_encounter}" in str(err.value)      # the message lists what may be used


def test_malformed_pattern_is_reported():
    with pytest.raises(InvalidFilenamePattern):
        build_filename("{member_name-SENT.pdf", member_name="A", policy_id="P",
                       case_encounter="E", today=TODAY)


def test_unknown_placeholders_helper():
    assert unknown_placeholders("{member_name}-{MMDDYY}.pdf") == []
    assert unknown_placeholders("{map_id}-{claim}.pdf") == ["map_id", "claim"]
    assert unknown_placeholders("{member_name") == ["(the pattern is malformed)"]
    assert "case_encounter" in ALLOWED_PLACEHOLDERS



def test_user_placeholder_drops_the_domain_and_illegal_characters():
    name = build_filename("{user}.pdf", member_name="A", policy_id="P", case_encounter="E",
                          user="MAP\\r.abdallah", today=TODAY)
    assert name == "r.abdallah.pdf"
