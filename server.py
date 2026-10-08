#!/usr/bin/env python3
"""
GS1 Bridge MCP — CSOAI Layer-0 legacy-bridge family.
Bridge GS1 product identity + EPCIS traceability (GTIN/SSCC/EPCIS) to ONE OS:
parse → map → govern (EU Digital Product Passport / traceability / food safety). Sibling of cobol-bridge-mcp.
Tools: parse_gs1 · map_to_modern · govern_traceability
"""
from mcp.server.mcpserver import MCPServer as FastMCP  # mcp 2.x: FastMCP renamed MCPServer
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import re

mcp = FastMCP("GS1 Bridge", instructions="Bridge GS1 / EPCIS supply-chain identity to ONE OS — parse, map, govern (EU DPP / traceability).")

import hashlib as _hl, time as _t, json as _j, os as _os
_SIGIL_LOG = _os.environ.get("SIGIL_LOG", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "bridge_sigil.log"))
def _sigil(op, body):
    try:
        prev = ""
        if _os.path.exists(_SIGIL_LOG):
            with open(_SIGIL_LOG) as f:
                ls = f.readlines()
                if ls: prev = _j.loads(ls[-1]).get("digest", "")
        ts = int(_t.time()); dg = _hl.sha256(f"{op}|{ts}|{prev[:8]}|{body}".encode()).hexdigest()[:16]
        _os.makedirs(_os.path.dirname(_SIGIL_LOG), exist_ok=True)
        with open(_SIGIL_LOG, "a") as f: f.write(_j.dumps({"ts": ts, "op": op, "body": body, "prev_digest": prev, "digest": dg}) + "\n")
        return dg
    except Exception: return ""

AI = {"01": "GTIN", "00": "SSCC", "10": "Batch/Lot", "17": "Expiry", "21": "Serial", "414": "GLN location"}
EPCIS = ["ObjectEvent", "AggregationEvent", "TransactionEvent", "TransformationEvent"]


class GS1Parsed(BaseModel):
    kind: str
    identifiers: Dict[str, str] = Field(default_factory=dict)
    epcis_event: Optional[str] = None
    gtin: Optional[str] = None


@mcp.tool()
def parse_gs1(data: str) -> GS1Parsed:
    """Parse a GS1 element string (AI-encoded) or an EPCIS event; extract GTIN + identifiers + event type."""
    ids = {}
    for ai, name in AI.items():
        m = re.search(r"\(" + ai + r"\)(\w+)", data)
        if m:
            ids[name] = m.group(1)
    if not ids:
        m = re.search(r"\b(\d{14})\b", data)
        if m: ids["GTIN"] = m.group(1)
    ev = next((e for e in EPCIS if e.lower() in data.lower()), None)
    kind = "EPCIS event" if ev else ("GS1 element string" if ids else "unknown")
    return GS1Parsed(kind=kind, identifiers=ids, epcis_event=ev, gtin=ids.get("GTIN"))


@mcp.tool()
def map_to_modern(data: str) -> Dict[str, Any]:
    """Map a GS1 / EPCIS record to a modern product-traceability event for ONE OS."""
    p = parse_gs1(data)
    return {"source": "GS1", "kind": p.kind, "event": p.epcis_event, "gtin": p.gtin,
            "identifiers": p.identifiers, "target": "modern traceability event"}


class Governance(BaseModel):
    risk_flags: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    attestable: bool = True
    note: str = ""


@mcp.tool()
def govern_traceability(data: str) -> Governance:
    """Governance: product traceability + Digital Product Passport surface (attestable for CSOAI)."""
    _sigil("G", "gs1|govern_traceability")
    p = parse_gs1(data)
    flags = []
    if not p.gtin:
        flags.append("No GTIN — product not uniquely identified; traceability incomplete")
    if p.epcis_event:
        flags.append(f"{p.epcis_event} — chain-of-custody step; sign for tamper-evident provenance")
    return Governance(risk_flags=flags,
                      frameworks=["GS1 / EPCIS", "EU Digital Product Passport (ESPR)", "Food Safety (FSMA 204)", "supply-chain due diligence (CSDDD)"],
                      note="CSOAI governs the bridge: each traceability event SIGIL-signed = verifiable provenance, source to shelf.")


# ---------------------------------------------------------------------------
# MCP 2026-07-28 wire - header-add migration (2026-10-08)
# ---------------------------------------------------------------------------
# stdio carries no HTTP headers, so Mcp-Method / Mcp-Name are not applicable to
# this transport at runtime. When gs1-bridge-mcp is exposed over HTTP, route the ingress
# through the vendored mcp2026_shim (ShimASGI): it validates Mcp-Method /
# Mcp-Name, injects params._meta.protocolVersion = "2026-07-28" into every
# request, strips Mcp-Session-Id and answers legacy initialize / server-discover
# locally (the session header is never emitted - stateless wire).
# Refs: MIGRATION_NOTE.md, MCP_2026_WIRE_MIGRATION_PLAN_2026-10-07.md (3) + (4).
# ---------------------------------------------------------------------------


def http_app():
    """ASGI app for HTTP exposure, wrapped in the 2026-07-28 wire shim.

    stdio (``mcp.run()``) needs no shim; this is the enable path once the
    server is fronted by an HTTP transport. Bodies are buffered, so responses
    are requested in JSON mode rather than SSE.
    """
    from mcp2026_shim import WIRE_2026, ShimASGI, ShimConfig

    return ShimASGI(
        mcp.streamable_http_app(json_response=True),
        ShimConfig(
            protocol_version=WIRE_2026,
            server_info={"name": "gs1-bridge-mcp", "version": "0.1.0"},
        ),
    )


def main():
    mcp.run()


if __name__ == "__main__":
    main()
