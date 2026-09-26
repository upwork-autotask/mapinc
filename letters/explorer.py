"""Open a folder in Windows Explorer on the machine running the server."""
import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def open_in_explorer(folder: Path) -> bool:
    """True when Explorer was started. Only ever called for a loopback request."""
    try:
        # explorer.exe returns 1 even on success, so the result is not waited for.
        subprocess.Popen(["explorer", str(folder)], close_fds=True)
        return True
    except OSError:
        log.exception("Could not start Explorer for %s", folder)
        return False
