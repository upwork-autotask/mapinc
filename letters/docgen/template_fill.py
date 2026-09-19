"""
Fill the Clinicals Request .docx template.

Every variable in the template is a Word content control (w:sdt) bound to a
document property via w:dataBinding/@w:xpath. We write each value into the
control's visible text AND into the property part it is bound to, so Word's
own binding refresh agrees with what we wrote.
"""
import copy
import datetime as dt
import io
import logging
import re
import zipfile

from lxml import etree

log = logging.getLogger(__name__)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC = "http://purl.org/dc/elements/1.1/"
EP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
COVER = "http://schemas.microsoft.com/office/2006/coverPageProps"
NS = {"w": W}

# last element of the binding xpath -> our field name
FIELD_BINDINGS = {
    "keywords": "policy_id",
    "category": "member_name",
    "PublishDate": "dob",
    "contentStatus": "admission",
    "Abstract": "attn",
    "Company": "client",
    "creator": "doctor",
}

# field name -> element (Clark notation) in each property part
CORE_PROPS = {
    "policy_id": f"{{{CP}}}keywords",
    "member_name": f"{{{CP}}}category",
    "admission": f"{{{CP}}}contentStatus",
    "doctor": f"{{{DC}}}creator",
}
APP_PROPS = {"client": f"{{{EP}}}Company"}
COVER_PROPS = {"attn": f"{{{COVER}}}Abstract", "dob_iso": f"{{{COVER}}}PublishDate"}

_XPATH_LAST = re.compile(r"/(?:[\w.]+:)?([\w.]+)(?:\[\d+\])?$")


def binding_name(xpath: str | None) -> str | None:
    """'/ns1:coreProperties[1]/ns1:keywords[1]' -> 'keywords'."""
    if not xpath:
        return None
    m = _XPATH_LAST.search(xpath)
    return m.group(1) if m else None


def format_date(d: dt.date) -> str:
    """Word's M/d/yyyy: no leading zeros."""
    return f"{d.month}/{d.day}/{d.year}"


def fill_template(template_bytes: bytes, values: dict) -> bytes:
    values = dict(values)
    if "dob" in values and values["dob"] is not None:
        dob = values["dob"]
        if not isinstance(dob, dt.date):
            raise TypeError("dob must be a datetime.date")
        values["dob_iso"] = f"{dob.year:04d}-{dob.month:02d}-{dob.day:02d}T00:00:00Z"
        values["dob"] = format_date(dob)

    src = zipfile.ZipFile(io.BytesIO(template_bytes))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/document.xml":
                data = _fill_document(data, values)
            elif item.filename == "docProps/core.xml":
                data = _set_props(data, CORE_PROPS, values)
            elif item.filename == "docProps/app.xml":
                data = _set_props(data, APP_PROPS, values)
            elif item.filename.startswith("customXml/item") and b"CoverPageProperties" in data:
                data = _set_props(data, COVER_PROPS, values)
            out.writestr(item, data)
    return buf.getvalue()


def _serialize(root) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _set_props(xml_bytes: bytes, mapping: dict, values: dict) -> bytes:
    root = etree.fromstring(xml_bytes)
    for field, tag in mapping.items():
        value = values.get(field)
        if value is None:
            continue
        el = root.find(tag)
        if el is None:
            el = etree.SubElement(root, tag)
        el.text = str(value)
    return _serialize(root)


def _fill_document(xml_bytes: bytes, values: dict) -> bytes:
    root = etree.fromstring(xml_bytes)
    filled: set[str] = set()
    for sdt in root.iter(f"{{{W}}}sdt"):
        pr = sdt.find("w:sdtPr", NS)
        binding = pr.find("w:dataBinding", NS) if pr is not None else None
        if binding is None:
            continue
        field = FIELD_BINDINGS.get(binding_name(binding.get(f"{{{W}}}xpath")))
        if field is None or values.get(field) is None:
            continue
        _set_sdt_text(sdt, pr, str(values[field]))
        if field == "dob":
            date_el = pr.find("w:date", NS)
            if date_el is not None:
                date_el.set(f"{{{W}}}fullDate", values["dob_iso"])
        filled.add(field)
    for field in FIELD_BINDINGS.values():
        if values.get(field) is not None and field not in filled:
            log.warning("Template has no content control bound for field %r", field)
    return _serialize(root)


def _set_sdt_text(sdt, pr, text: str) -> None:
    for plc in pr.findall("w:showingPlcHdr", NS):
        pr.remove(plc)
    content = sdt.find("w:sdtContent", NS)
    if content is None:
        content = etree.SubElement(sdt, f"{{{W}}}sdtContent")
    rpr = _pick_run_properties(sdt, content)

    paragraphs = content.findall("w:p", NS)
    if paragraphs:  # block-level control: keep first paragraph (and its pPr), drop the rest
        container = paragraphs[0]
        for extra in paragraphs[1:]:
            content.remove(extra)
        for child in list(container):
            if child.tag != f"{{{W}}}pPr":
                container.remove(child)
    else:  # inline control
        container = content
        for child in list(container):
            container.remove(child)

    run = etree.SubElement(container, f"{{{W}}}r")
    if rpr is not None:
        run.append(rpr)
    t = etree.SubElement(run, f"{{{W}}}t")
    t.text = text
    t.set(f"{{{XML_NS}}}space", "preserve")


def _pick_run_properties(sdt, content):
    """
    Formatting for the new text, in order of preference:
    1. the control's existing run, if it is real text (not the grey placeholder style);
    2. the nearest preceding run with real text (the label) — its rPr, or none if it
       simply inherits the paragraph style;
    3. Arial 15pt #333333 (the template's header-block style).
    """
    for run in content.iter(f"{{{W}}}r"):
        rpr = run.find("w:rPr", NS)
        if rpr is not None and rpr.find("w:rStyle[@w:val='PlaceholderText']", NS) is None:
            return copy.deepcopy(rpr)
    prev = sdt.getprevious()
    while prev is not None:
        if prev.tag == f"{{{W}}}r" and "".join(prev.itertext()).strip():
            rpr = prev.find("w:rPr", NS)
            if rpr is None:
                return None  # the label inherits the paragraph style; so should the value
            rpr = copy.deepcopy(rpr)
            for style in rpr.findall("w:rStyle", NS):
                rpr.remove(style)
            return rpr
        prev = prev.getprevious()
    rpr = etree.Element(f"{{{W}}}rPr")
    fonts = etree.SubElement(rpr, f"{{{W}}}rFonts")
    for attr in ("ascii", "hAnsi", "cs"):
        fonts.set(f"{{{W}}}{attr}", "Arial")
    etree.SubElement(rpr, f"{{{W}}}color").set(f"{{{W}}}val", "333333")
    etree.SubElement(rpr, f"{{{W}}}sz").set(f"{{{W}}}val", "30")
    etree.SubElement(rpr, f"{{{W}}}szCs").set(f"{{{W}}}val", "30")
    return rpr


def missing_bindings(template_bytes: bytes) -> set[str]:
    """Field names (see FIELD_BINDINGS) that have no bound content control in the template."""
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(template_bytes)).read("word/document.xml"))
    found = {
        FIELD_BINDINGS[name]
        for binding in root.iter(f"{{{W}}}dataBinding")
        if (name := binding_name(binding.get(f"{{{W}}}xpath"))) in FIELD_BINDINGS
    }
    return set(FIELD_BINDINGS.values()) - found
