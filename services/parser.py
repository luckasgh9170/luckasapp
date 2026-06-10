from __future__ import annotations

import base64
import hashlib
import re
from urllib.parse import parse_qs, unquote, urlparse

import orjson

from models.config import ProxyConfig


SUPPORTED_PROTOCOLS = (
    "vmess",
    "vless",
    "trojan",
    "ss",
    "ssr",
    "shadowsocks",
    "hysteria",
    "hysteria2",
    "hy2",
    "tuic",
)
CONFIG_RE = re.compile(
    r"(?P<url>(?:vmess|vless|trojan|ss|ssr|shadowsocks|hysteria|hysteria2|hy2|tuic)://[^\s'\"]+)",
    re.I,
)


def stable_id(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _decode_b64(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded)


def extract_configs(text: str) -> list[ProxyConfig]:
    found = CONFIG_RE.findall(text)
    if not found and text.strip():
        try:
            decoded = _decode_b64(text.strip()).decode("utf-8", "ignore")
            found = CONFIG_RE.findall(decoded)
        except Exception:
            found = []

    configs: list[ProxyConfig] = []
    seen: set[str] = set()
    for raw in found:
        raw = raw.strip()
        if raw in seen:
            continue
        seen.add(raw)
        parsed = parse_config(raw)
        if parsed:
            configs.append(parsed)
    return configs


def parse_config(raw: str) -> ProxyConfig | None:
    try:
        protocol = raw.split("://", 1)[0].lower()
        if protocol == "vmess":
            return _parse_vmess(raw)
        if protocol == "ssr":
            return _parse_ssr(raw)
        if protocol in SUPPORTED_PROTOCOLS:
            normalized = {"ss": "shadowsocks", "hy2": "hysteria2"}.get(protocol, protocol)
            return _parse_uri(raw, normalized)
        return None
    except Exception:
        return None


def _parse_vmess(raw: str) -> ProxyConfig | None:
    payload = raw.split("://", 1)[1]
    try:
        data = orjson.loads(_decode_b64(payload))
    except Exception:
        return None
    host = str(data.get("add", ""))
    port = int(data.get("port", 0) or 0)
    name = str(data.get("ps") or host or "VMess")
    if not host or not port:
        return None
    return ProxyConfig(id=stable_id(raw), protocol="vmess", raw=raw, name=name, host=host, port=port)


def _parse_uri(raw: str, protocol: str) -> ProxyConfig | None:
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    host = parsed.hostname or ""
    port = _safe_port(parsed)
    qs = parse_qs(parsed.query)
    name = unquote(parsed.fragment or qs.get("remarks", [""])[0] or host or protocol.upper())
    if not host or not port:
        return None
    return ProxyConfig(id=stable_id(raw), protocol=protocol, raw=raw, name=name, host=host, port=port)


def _parse_ssr(raw: str) -> ProxyConfig | None:
    payload = raw.split("://", 1)[1]
    try:
        decoded = _decode_b64(payload).decode("utf-8", "ignore")
        main, _, params_text = decoded.partition("/?")
        parts = main.split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 0
        params = parse_qs(params_text)
        remarks = params.get("remarks", [""])[0]
        name = _decode_b64(remarks).decode("utf-8", "ignore") if remarks else host
    except Exception:
        return None
    if not host or not port:
        return None
    return ProxyConfig(id=stable_id(raw), protocol="ssr", raw=raw, name=name, host=host, port=port)


def _safe_port(parsed) -> int:
    try:
        return parsed.port or 0
    except ValueError:
        return 0
