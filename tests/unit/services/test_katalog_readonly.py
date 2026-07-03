"""Write-boundary guarantee for the catalog agent (§8, D8).

Activation is a human-only operation: the agent's write tools save drafts through
`KatalogEntwurfDienst` and can NEVER promote one — `bundle_aktivieren` lives only on the bundle
service, called only by the API route (a human request on the confirm card). This is enforced
structurally: every module under `shared/services/katalog` EXCEPT the bundle service itself must be
free of any *code reference* to `bundle_aktivieren`. The check is AST-based, so a docstring that
merely names the boundary does not count — only an actual attribute/name reference does. A future
edit that wires activation into a tool, the agent, or the facade fails here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import shared.services.katalog as katalog_pkg

# The one module that legitimately owns activation (invoked only by the API route).
_AKTIVIERUNG_ERLAUBT = {"service.py"}
_VERBOTEN = "bundle_aktivieren"


def _referenziert(quelle: str, name: str) -> bool:
    """True if the source references `name` as an attribute or bare name (ignores strings/comments)."""
    baum = ast.parse(quelle)
    for node in ast.walk(baum):
        if isinstance(node, ast.Attribute) and node.attr == name:
            return True
        if isinstance(node, ast.Name) and node.id == name:
            return True
    return False


def test_write_tools_never_reference_activation() -> None:
    paket = Path(katalog_pkg.__file__).parent
    treffer = {
        p.name
        for p in paket.glob("*.py")
        if p.name not in _AKTIVIERUNG_ERLAUBT
        and _referenziert(p.read_text(encoding="utf-8"), _VERBOTEN)
    }
    assert not treffer, f"{_VERBOTEN} reachable from non-service modules: {sorted(treffer)}"
