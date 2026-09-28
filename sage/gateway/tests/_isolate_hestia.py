"""Gateway tests never reach the seat's LIVE hestia daemon. Imported first by conftest.py and by
every test file that also runs as a plain script.

WHY (McNugget, 2026-09-28): a test that builds a real BeingGateClient and calls gate() loads
hestia's single-gate/mechanism, which discover the daemon at $HESTIA_ENDPOINT, then
$HESTIA_HOME/endpoint -- on a seat, the live one -- and connecting MINTS the test's plugin id as a
member of the seat's real society. dp found `test-being` among 12 phantom members.

TWO LAYERS, UNCONDITIONAL (GPT, review of #257: the first cut used `setdefault`, so a seat that
exports its ordinary HESTIA_ENDPOINT still ran the tests against its real society -- an inherited
runtime setting is not consent):
  1. HESTIA_ENDPOINT is OVERWRITTEN with a `.invalid` host (RFC 2606: guaranteed never to resolve),
     not a port-9 convention that a listener could someday answer.
  2. urllib.request.urlopen refuses, in-process, any request to the seat's live daemon address --
     127.0.0.1/localhost/::1 on the endpoint's port (7711 by default, else the port in
     $HESTIA_HOME/endpoint). That also covers code that hard-codes the address rather than asking
     for the endpoint (sage/gateway/hestia_witness.py's _ENDPOINT).

The ONLY way back to a real daemon is the explicit opt-in SAGE_TEST_LIVE_HESTIA=1, for a
deliberate integration run against a daemon that run owns.
"""
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ISOLATED_ENDPOINT = "http://hestia-isolated-for-tests.invalid/mcp"
OPT_IN = "SAGE_TEST_LIVE_HESTIA"
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _live_ports() -> set:
    ports = {7711}
    home = Path(os.getenv("HESTIA_HOME") or Path.home() / ".hestia")
    try:
        port = urllib.parse.urlparse((home / "endpoint").read_text().strip()).port
        if port:
            ports.add(port)
    except (OSError, ValueError):
        pass
    return ports


def is_live_daemon_url(url: str, ports: set) -> bool:
    u = urllib.parse.urlparse(url)
    return (u.hostname or "") in _LOOPBACK and (u.port or 80) in ports


def isolate() -> None:
    if os.getenv(OPT_IN) == "1":
        return
    os.environ["HESTIA_ENDPOINT"] = ISOLATED_ENDPOINT
    if getattr(urllib.request.urlopen, "_sage_isolated", False):
        return
    ports, real = _live_ports(), urllib.request.urlopen

    def guarded(url, *args, **kwargs):
        target = url.full_url if isinstance(url, urllib.request.Request) else str(url)
        if is_live_daemon_url(target, ports):
            raise urllib.error.URLError(
                f"test isolation: refused a request to the seat's live hestia daemon ({target}). "
                f"Tests must not reach it; set {OPT_IN}=1 only for a deliberate integration run.")
        return real(url, *args, **kwargs)

    guarded._sage_isolated = True
    urllib.request.urlopen = guarded


isolate()
