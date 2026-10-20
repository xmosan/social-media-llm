"""Bounded public HTTPS reads, with DNS checked once and the connection pinned."""
import ipaddress
import socket
import time
from urllib.parse import urlsplit

import certifi
import urllib3


def _public_address(value):
    address = ipaddress.ip_address(value)
    if not address.is_global or address.is_multicast:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        # Do not allow transition mechanisms to carry a private IPv4 destination.
        if address.ipv4_mapped or address.sixtofour or address.teredo:
            return False
        if address in ipaddress.ip_network("64:ff9b::/96"):
            return False
    return True


def fetch_public_document(url, *, maximum=2 * 1024 * 1024):
    """Return bytes without redirects, proxies, credentials or compressed bodies.

    Connecting to the validated IP prevents a second DNS lookup from rebinding
    to a private address. TLS SNI and certificate validation still use the host.
    """
    try:
        parsed = urlsplit(url)
        if (len(url) > 2048 or parsed.scheme != "https" or not parsed.hostname
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.fragment or "\\" in url or any(ord(c) < 33 for c in url)):
            raise ValueError()
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        addresses = {a[4][0] for a in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
        if not addresses or any(not _public_address(a) for a in addresses):
            raise ValueError()
    except (ValueError, TypeError, UnicodeError, OSError):
        raise ValueError("Use a public HTTPS page. Private addresses and custom ports are not supported.") from None

    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    try:
        with urllib3.HTTPSConnectionPool(
            sorted(addresses)[0], port=443, server_hostname=host, assert_hostname=host,
            cert_reqs="CERT_REQUIRED", ca_certs=certifi.where(),
            timeout=urllib3.Timeout(connect=3, read=5), retries=False,
        ) as pool:
            response = pool.urlopen("GET", target, headers={
                "Host": host, "User-Agent": "SabeelSourceReader/1.0", "Accept-Encoding": "identity",
            }, assert_same_host=False, redirect=False, preload_content=False)
            try:
                if response.status != 200:
                    raise ValueError("The page could not be imported. Use its final HTTPS address or paste the text.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise ValueError("Paste the source text instead; this page uses an unsupported encoding.")
                kind = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if kind not in {"text/html", "text/plain", "application/xhtml+xml"}:
                    raise ValueError("Use an HTML or plain-text page.")
                data, deadline = bytearray(), time.monotonic() + 20
                for chunk in response.stream(65536, decode_content=False):
                    data.extend(chunk)
                    if len(data) > maximum or time.monotonic() > deadline:
                        raise ValueError("The page is too large or slow to import. Paste the relevant text instead.")
                return bytes(data)
            finally:
                response.close()
    except (urllib3.exceptions.HTTPError, OSError):
        raise ValueError("The page could not be imported. Please try again or paste the source text.") from None
