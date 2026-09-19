import datetime as dt

import pytest

from letters.docgen.pdf_convert import ConversionError, convert, word_available


def _docx(tmp_path):
    src = tmp_path / "a.docx"
    src.write_bytes(b"not really a docx")
    return src


def test_fake_converter_writes_a_pdf_and_creates_parent_dir(tmp_path):
    out = tmp_path / "sub" / "a.pdf"
    convert(_docx(tmp_path), out, converter="fake")
    assert out.read_bytes().startswith(b"%PDF")


def test_missing_source_raises(tmp_path):
    with pytest.raises(ConversionError):
        convert(tmp_path / "nope.docx", tmp_path / "a.pdf", converter="fake")


def test_unknown_converter_raises(tmp_path):
    with pytest.raises(ConversionError):
        convert(_docx(tmp_path), tmp_path / "a.pdf", converter="bogus")


def test_default_converter_comes_from_settings(tmp_path, settings):
    settings.PDF_CONVERTER = "fake"
    out = tmp_path / "a.pdf"
    convert(_docx(tmp_path), out)
    assert out.exists()


@pytest.mark.word
@pytest.mark.skipif(not word_available(), reason="Microsoft Word not installed")
def test_word_converts_the_filled_template(tmp_path, template_bytes):
    from letters.docgen.template_fill import fill_template

    src = tmp_path / "letter.docx"
    src.write_bytes(fill_template(template_bytes, dict(
        policy_id="WT-1", member_name="JOHN SMITH", dob=dt.date(1953, 5, 22), admission="9/15/2026")))
    out = tmp_path / "letter.pdf"
    convert(src, out, converter="word")
    assert out.read_bytes()[:5] == b"%PDF-"
    assert out.stat().st_size > 10_000  # a real one-page letter with the logo
