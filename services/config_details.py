from __future__ import annotations

import base64
from urllib.parse import parse_qs, unquote, urlparse

import orjson

from models.repository import ExtractedConfigInfo


def _decode_b64(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded)


def extract_config_info(raw: str) -> ExtractedConfigInfo | None:
    try:
        protocol = raw.split("://", 1)[0].lower()
        if protocol == "vmess":
            return _vmess(raw)
        if protocol == "ssr":
            return _ssr(raw)
        if protocol in {"vless", "trojan", "ss", "shadowsocks", "hysteria", "hysteria2", "hy2", "tuic"}:
            normalized = {"ss": "shadowsocks", "hy2": "hysteria2"}.get(protocol, protocol)
            return _uri(raw, normalized)
        return None
    except Exception:
        return None


def _vmess(raw: str) -> ExtractedConfigInfo | None:
    try:
        data = orjson.loads(_decode_b64(raw.split("://", 1)[1]))
    except Exception:
        return None
    return ExtractedConfigInfo(
        protocol="vmess",
        server=str(data.get("add", "")),
        port=int(data.get("port", 0) or 0),
        uuid=str(data.get("id", "")),
        transport_type=str(data.get("net", "tcp")),
        tls=str(data.get("tls", "")).lower() == "tls",
        reality=False,
        sni=str(data.get("sni") or data.get("host") or ""),
    )


def _uri(raw: str, protocol: str) -> ExtractedConfigInfo | None:
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    qs = parse_qs(parsed.query)
    security = qs.get("security", [""])[0].lower()
    tls = security in {"tls", "reality"}
    uuid = parsed.username or qs.get("uuid", [""])[0]
    return ExtractedConfigInfo(
        protocol=protocol,
        server=parsed.hostname or "",
        port=_safe_port(parsed),
        uuid=unquote(uuid),
        transport_type=qs.get("type", qs.get("network", ["tcp"]))[0],
        tls=tls,
        reality=security == "reality",
        sni=qs.get("sni", qs.get("host", [""]))[0],
    )


def _ssr(raw: str) -> ExtractedConfigInfo | None:
    try:
        decoded = _decode_b64(raw.split("://", 1)[1]).decode("utf-8", "ignore")
        main, _, _params_text = decoded.partition("/?")
        parts = main.split(":")
        return ExtractedConfigInfo(protocol="ssr", server=parts[0], port=int(parts[1]) if len(parts) > 1 else 0)
    except Exception:
        return None


def _safe_port(parsed) -> int:
    try:
        return parsed.port or 0
    except ValueError:
        return 0
