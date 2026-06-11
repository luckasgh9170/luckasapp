from __future__ import annotations

import base64
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import orjson

from models.config import ProxyConfig


def _decode_b64(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded)


def export_xray_config(
    config: ProxyConfig,
    path: Path,
    *,
    socks_port: int | None = 10808,
    http_port: int | None = 10809,
    loglevel: str = "warning",
    dns_server: str = "1.1.1.1",
    prefer_ipv6: bool = False,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    inbounds = []
    if socks_port is not None:
        inbounds.append(
            {
                "tag": "socks-in",
                "port": socks_port,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": {"udp": True},
            }
        )
    if http_port is not None:
        inbounds.append(
            {
                "tag": "http-in",
                "port": http_port,
                "listen": "127.0.0.1",
                "protocol": "http",
            }
        )
    outbound = _build_outbound(config)
    document = {
        "log": {"loglevel": loglevel},
        "dns": {
            "servers": [dns_server or "1.1.1.1", "8.8.8.8"],
            "queryStrategy": "UseIP" if prefer_ipv6 else "UseIPv4",
        },
        "inbounds": inbounds,
        "outbounds": [outbound, {"protocol": "freedom", "tag": "direct"}],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
                {"type": "field", "network": "tcp,udp", "outboundTag": "proxy"},
            ],
        },
    }
    path.write_bytes(orjson.dumps(document, option=orjson.OPT_INDENT_2))
    return path


def _build_outbound(config: ProxyConfig) -> dict:
    if config.protocol == "vmess":
        return _vmess(config)
    if config.protocol == "vless":
        return _vless(config)
    if config.protocol == "trojan":
        return _trojan(config)
    if config.protocol == "shadowsocks":
        return _shadowsocks(config)
    raise ValueError(f"Unsupported core export protocol: {config.protocol}")


def _vmess(config: ProxyConfig) -> dict:
    data = orjson.loads(_decode_b64(config.raw.split("://", 1)[1]))
    return {
        "tag": "proxy",
        "protocol": "vmess",
        "settings": {
            "vnext": [
                {
                    "address": data.get("add", config.host),
                    "port": int(data.get("port", config.port)),
                    "users": [
                        {
                            "id": data.get("id", ""),
                            "alterId": int(data.get("aid", 0) or 0),
                            "security": data.get("scy", "auto"),
                        }
                    ],
                }
            ]
        },
        "streamSettings": _stream_settings(
            network=str(data.get("net", "tcp")),
            security=str(data.get("tls", "")),
            host=str(data.get("host", "")),
            path=str(data.get("path", "")),
            sni=str(data.get("sni", "")),
        ),
    }


def _vless(config: ProxyConfig) -> dict:
    parsed = urlparse(config.raw)
    qs = parse_qs(parsed.query)
    user = {"id": parsed.username or "", "encryption": qs.get("encryption", ["none"])[0]}
    if qs.get("flow", [""])[0]:
        user["flow"] = qs.get("flow", [""])[0]
    return {
        "tag": "proxy",
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": config.host,
                    "port": config.port,
                    "users": [user],
                }
            ]
        },
        "streamSettings": _stream_settings(
            network=qs.get("type", ["tcp"])[0],
            security=qs.get("security", [""])[0],
            host=qs.get("host", [""])[0],
            path=qs.get("path", [""])[0],
            sni=qs.get("sni", [""])[0],
            fingerprint=qs.get("fp", [""])[0],
            public_key=qs.get("pbk", [""])[0],
            short_id=qs.get("sid", [""])[0],
            spider_x=qs.get("spx", [""])[0],
            service_name=qs.get("serviceName", qs.get("service", [""]))[0],
        ),
    }


def _trojan(config: ProxyConfig) -> dict:
    parsed = urlparse(config.raw)
    qs = parse_qs(parsed.query)
    return {
        "tag": "proxy",
        "protocol": "trojan",
        "settings": {
            "servers": [{"address": config.host, "port": config.port, "password": parsed.username or ""}]
        },
        "streamSettings": _stream_settings(
            network=qs.get("type", ["tcp"])[0],
            security=qs.get("security", ["tls"])[0],
            host=qs.get("host", [""])[0],
            path=qs.get("path", [""])[0],
            sni=qs.get("sni", [""])[0],
            fingerprint=qs.get("fp", [""])[0],
            service_name=qs.get("serviceName", qs.get("service", [""]))[0],
        ),
    }


def _shadowsocks(config: ProxyConfig) -> dict:
    parsed = urlparse(config.raw)
    method = "aes-128-gcm"
    password = ""
    if parsed.username:
        try:
            decoded = _decode_b64(parsed.username).decode("utf-8", "ignore")
            method, password = decoded.split(":", 1)
        except Exception:
            method = parsed.username
            password = parsed.password or ""
    return {
        "tag": "proxy",
        "protocol": "shadowsocks",
        "settings": {"servers": [{"address": config.host, "port": config.port, "method": method, "password": password}]},
    }


def _stream_settings(
    *,
    network: str,
    security: str,
    host: str,
    path: str,
    sni: str = "",
    fingerprint: str = "",
    public_key: str = "",
    short_id: str = "",
    spider_x: str = "",
    service_name: str = "",
) -> dict:
    settings: dict = {"network": network or "tcp", "security": security or "none"}
    server_name = sni or host
    if security == "tls":
        tls_settings = {"serverName": server_name} if server_name else {}
        if fingerprint:
            tls_settings["fingerprint"] = fingerprint
        tls_settings["allowInsecure"] = False
        settings["tlsSettings"] = tls_settings
    if security == "reality":
        reality_settings = {
            "serverName": server_name,
            "fingerprint": fingerprint or "chrome",
            "publicKey": public_key,
            "shortId": short_id,
            "spiderX": spider_x or "/",
        }
        settings["realitySettings"] = {key: value for key, value in reality_settings.items() if value}
    if network == "ws":
        ws_settings = {"path": path or "/"}
        if host:
            ws_settings["headers"] = {"Host": host}
        settings["wsSettings"] = ws_settings
    if network == "grpc":
        settings["grpcSettings"] = {"serviceName": service_name or (path.lstrip("/") if path else "")}
    return settings
