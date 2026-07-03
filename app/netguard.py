"""Guard for server-side fetches of user-supplied URLs (image proxy, sheet
fetch, link resolution). Blocks requests that would reach private/internal
addresses (SSRF): localhost, RFC1918 ranges, link-local/cloud-metadata, etc.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def is_public_http_url(url: str) -> bool:
    """True only for http(s) URLs whose host resolves to public addresses."""
    try:
        p = urlparse(url or "")
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return False
        return True
    except Exception:  # noqa: BLE001 — unresolvable/malformed = not fetchable
        return False
