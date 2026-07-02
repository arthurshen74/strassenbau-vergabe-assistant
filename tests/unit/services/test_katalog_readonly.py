"""Read-only guarantee for the Katalog-Chat service (§10.5).

Phase 1 is reads only, by construction: the katalog_chat service must not be able to reach the write
surface (the bundle service `KatalogService.entwurf_speichern` / `bundle_aktivieren` and its
validator). A fresh interpreter imports the chat service and asserts neither write module was pulled
into the transitive import graph — so a future edit that accidentally wires a write path in fails
here.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import shared

_WRITE_MODULES = (
    "shared.services.katalog.service",
    "shared.services.katalog.validierung",
)


def test_katalog_chat_service_imports_no_write_surface() -> None:
    server_dir = Path(shared.__file__).resolve().parents[1]
    verboten = ", ".join(repr(m) for m in _WRITE_MODULES)
    code = (
        "import sys\n"
        "import shared.services.katalog.chat_service  # noqa: F401\n"
        f"treffer = {{{verboten}}} & set(sys.modules)\n"
        "assert not treffer, f'write surface reachable: {treffer}'\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "PYTHONPATH": str(server_dir)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
