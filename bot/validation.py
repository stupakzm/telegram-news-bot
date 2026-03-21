"""URL validation utilities for RSS feed safety."""
import ipaddress
import socket
from urllib.parse import urlparse


def validate_rss_url(url: str) -> bool:
    """
    Validate an RSS feed URL is safe to fetch.

    Rejects:
    - Non http/https schemes
    - Private IP ranges (RFC 1918: 10.x, 172.16-31.x, 192.168.x)
    - Loopback (127.x, ::1)
    - Link-local (169.254.x.x)
    - CGNAT (100.64.0.0/10)

    Returns True if URL is safe, False otherwise.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    # Scheme check
    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # Resolve hostname to IP for private range check
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # hostname is a domain name, resolve it
        try:
            resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            if not resolved:
                return False
            # Check first resolved IP
            ip_str = resolved[0][4][0]
            addr = ipaddress.ip_address(ip_str)
        except (socket.gaierror, OSError):
            # Cannot resolve — allow (may be temporary DNS issue; fetch will fail later)
            return True

    # Block private, loopback, link-local, and reserved ranges
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        return False

    # Explicit CGNAT check (100.64.0.0/10) — is_private covers this in Python 3.11+
    # but we check explicitly for clarity
    if isinstance(addr, ipaddress.IPv4Address):
        cgnat = ipaddress.IPv4Network("100.64.0.0/10")
        if addr in cgnat:
            return False

    return True
