"""
Turn a .docx into a .pdf. `word` (default) automates Microsoft Word through
COM; `libreoffice` shells out to soffice; `fake` writes a minimal PDF for tests.
"""
import logging
import shutil
import subprocess
import threading
from pathlib import Path

from django.conf import settings

log = logging.getLogger(__name__)

WINWORD = Path(r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE")
WD_EXPORT_FORMAT_PDF = 17
WD_DO_NOT_SAVE_CHANGES = 0

MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


class ConversionError(RuntimeError):
    pass


def word_available() -> bool:
    return WINWORD.exists()


def convert(docx_path: Path, pdf_path: Path, converter: str | None = None) -> None:
    converter = (converter or settings.PDF_CONVERTER).lower()
    docx_path, pdf_path = Path(docx_path), Path(pdf_path)
    if not docx_path.exists():
        raise ConversionError(f"Source document not found: {docx_path}")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    if converter == "fake":
        pdf_path.write_bytes(MINIMAL_PDF)
    elif converter == "word":
        _convert_word(docx_path, pdf_path, settings.WORD_TIMEOUT_SECONDS)
    elif converter == "libreoffice":
        _convert_libreoffice(docx_path, pdf_path, settings.WORD_TIMEOUT_SECONDS)
    else:
        raise ConversionError(f"Unknown pdf_converter {converter!r} in MAPINC_PDF_CONVERTER")

    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise ConversionError(f"{converter} produced no PDF at {pdf_path}")


# --- Word -------------------------------------------------------------------

_word_lock = threading.Lock()  # one Word conversion at a time, process-wide


def _convert_word(docx_path: Path, pdf_path: Path, timeout: int) -> None:
    """Run Word in a worker thread so a hung WINWORD can be abandoned and killed."""
    with _word_lock:
        before = _winword_pids()
        errors: list[BaseException] = []
        worker = threading.Thread(target=_word_export, args=(docx_path, pdf_path, errors), daemon=True)
        worker.start()
        worker.join(timeout)
        if worker.is_alive():
            for pid in _winword_pids() - before:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
            raise ConversionError(f"Word did not finish within {timeout}s; its process was killed")
        if errors:
            raise ConversionError(f"Word failed: {errors[0]}") from errors[0]


def _word_export(docx_path: Path, pdf_path: Path, errors: list) -> None:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    word = doc = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(docx_path), ReadOnly=True, AddToRecentFiles=False)
        doc.ExportAsFixedFormat(str(pdf_path), WD_EXPORT_FORMAT_PDF)
    except BaseException as exc:  # noqa: BLE001 - surfaced to the caller thread
        errors.append(exc)
    finally:
        # Release the COM proxies in order (document, then application) *before*
        # CoUninitialize, otherwise their late release talks to a dead Word process.
        if doc is not None:
            try:
                doc.Close(WD_DO_NOT_SAVE_CHANGES)
            except Exception:  # noqa: BLE001
                log.exception("Document.Close failed")
            doc = None
        if word is not None:
            try:
                word.Quit()
            except Exception:  # noqa: BLE001
                log.exception("Word.Quit failed")
            word = None
        pythoncom.CoUninitialize()


def _winword_pids() -> set[int]:
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq WINWORD.EXE", "/FO", "CSV", "/NH"],
        capture_output=True, text=True).stdout
    pids = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.strip().split('","')]
        if len(parts) >= 2 and parts[0].upper() == "WINWORD.EXE" and parts[1].isdigit():
            pids.add(int(parts[1]))
    return pids


# --- LibreOffice ------------------------------------------------------------

def _convert_libreoffice(docx_path: Path, pdf_path: Path, timeout: int) -> None:
    soffice = shutil.which("soffice") or r"C:\Program Files\LibreOffice\program\soffice.exe"
    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pdf_path.parent), str(docx_path)],
        capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise ConversionError(result.stderr.strip() or "LibreOffice conversion failed")
    produced = pdf_path.parent / f"{docx_path.stem}.pdf"
    if produced != pdf_path:
        produced.replace(pdf_path)
