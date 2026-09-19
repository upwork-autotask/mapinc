import datetime as dt
import io
import zipfile

import pytest
from lxml import etree

from letters.docgen.template_fill import FIELD_BINDINGS, binding_name, fill_template, format_date

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
CHANGED_PARTS = {"word/document.xml", "docProps/core.xml", "docProps/app.xml", "customXml/item1.xml"}

SAMPLE = dict(
    policy_id="WT-123456",
    member_name="JOHN SMITH",
    dob=dt.date(1953, 5, 22),
    admission="9/15/2026",
    attn="UR DEPARTMENT",
    client="WORLDTRIPS",
    doctor="RICHARD ABDALLAH",
)


def _sdt_texts(docx_bytes: bytes) -> dict[str, list[str]]:
    """Map binding name -> text of every content control bound to it, in document order."""
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(docx_bytes)).read("word/document.xml"))
    out: dict[str, list[str]] = {}
    for sdt in root.iter(f"{{{W}}}sdt"):
        binding = sdt.find("w:sdtPr/w:dataBinding", NS)
        if binding is None:
            continue
        name = binding_name(binding.get(f"{{{W}}}xpath"))
        text = "".join(t.text or "" for t in sdt.iter(f"{{{W}}}t"))
        out.setdefault(name, []).append(text)
    return out


def test_binding_name_takes_last_xpath_element():
    assert binding_name("/ns1:coreProperties[1]/ns1:keywords[1]") == "keywords"
    assert binding_name("/ns0:CoverPageProperties[1]/ns0:PublishDate[1]") == "PublishDate"
    assert binding_name("") is None


def test_format_date_has_no_leading_zeros():
    assert format_date(dt.date(1953, 5, 22)) == "5/22/1953"
    assert format_date(dt.date(2026, 12, 1)) == "12/1/2026"


def test_template_contains_every_expected_binding(template_bytes):
    assert set(FIELD_BINDINGS) <= set(_sdt_texts(template_bytes))


def test_fills_every_bound_control_including_duplicates(template_bytes):
    texts = _sdt_texts(fill_template(template_bytes, SAMPLE))
    assert texts["keywords"] == ["WT-123456"]
    assert texts["category"] == ["JOHN SMITH", "JOHN SMITH"]
    assert texts["PublishDate"] == ["5/22/1953"]
    assert texts["contentStatus"] == ["9/15/2026", "9/15/2026"]
    assert texts["Abstract"] == ["UR DEPARTMENT"]
    assert texts["Company"] == ["WORLDTRIPS", "WORLDTRIPS"]
    assert texts["creator"] == ["RICHARD ABDALLAH", "RICHARD ABDALLAH"]
    assert texts["subject"] == ["CLINICALS REQUEST"]  # untouched


def test_placeholder_markers_removed_from_filled_controls(template_bytes):
    root = etree.fromstring(
        zipfile.ZipFile(io.BytesIO(fill_template(template_bytes, SAMPLE))).read("word/document.xml"))
    assert root.find(".//w:showingPlcHdr", NS) is None
    assert root.find(".//w:sdt//w:rStyle[@w:val='PlaceholderText']", NS) is None
    date_ctl = root.find(".//w:sdt/w:sdtPr/w:date", NS)
    assert date_ctl.get(f"{{{W}}}fullDate") == "1953-05-22T00:00:00Z"


def test_document_properties_updated(template_bytes):
    z = zipfile.ZipFile(io.BytesIO(fill_template(template_bytes, SAMPLE)))
    core = z.read("docProps/core.xml").decode()
    app = z.read("docProps/app.xml").decode()
    cover = z.read("customXml/item1.xml").decode()
    assert "<cp:keywords>WT-123456</cp:keywords>" in core
    assert "<cp:category>JOHN SMITH</cp:category>" in core
    assert "<cp:contentStatus>9/15/2026</cp:contentStatus>" in core
    assert "<dc:creator>RICHARD ABDALLAH</dc:creator>" in core
    assert "<Company>WORLDTRIPS</Company>" in app
    assert "<Abstract>UR DEPARTMENT</Abstract>" in cover
    assert "<PublishDate>1953-05-22T00:00:00Z</PublishDate>" in cover


def test_untouched_parts_are_byte_identical(template_bytes):
    src = zipfile.ZipFile(io.BytesIO(template_bytes))
    out = zipfile.ZipFile(io.BytesIO(fill_template(template_bytes, SAMPLE)))
    assert src.namelist() == out.namelist()
    for name in src.namelist():
        if name not in CHANGED_PARTS:
            assert src.read(name) == out.read(name), name
    assert out.testzip() is None


def test_missing_values_leave_controls_alone(template_bytes):
    texts = _sdt_texts(fill_template(template_bytes, {"policy_id": "X"}))
    assert texts["keywords"] == ["X"]
    assert texts["Company"] == ["WORLDTRIPS", "WORLDTRIPS"]
    assert texts["category"] == ["[Category]", "[Category]"]


def test_dob_must_be_a_date(template_bytes):
    with pytest.raises(TypeError):
        fill_template(template_bytes, {"dob": "5/22/1953"})


def test_body_sentence_values_inherit_body_formatting(template_bytes):
    """The Member Name inside the body sentence must not pick up the 15pt header style."""
    root = etree.fromstring(
        zipfile.ZipFile(io.BytesIO(fill_template(template_bytes, SAMPLE))).read("word/document.xml"))
    category_sdts = [
        s for s in root.iter(f"{{{W}}}sdt")
        if binding_name(s.find("w:sdtPr/w:dataBinding", NS).get(f"{{{W}}}xpath")
                        if s.find("w:sdtPr/w:dataBinding", NS) is not None else None) == "category"]
    header_run, body_run = (s.find(".//w:r", NS) for s in category_sdts)
    assert header_run.find("w:rPr/w:sz", NS).get(f"{{{W}}}val") == "30"
    assert body_run.find("w:rPr/w:sz", NS) is None
