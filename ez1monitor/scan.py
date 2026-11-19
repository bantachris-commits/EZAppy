"""Find EZ1 inverters on the local network by probing the local-API port."""

from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor

from .ez1 import EZ1Client, EZ1Error


def local_networks() -> list[ipaddress.IPv4Network]:
    """Best guess at this computer's LAN(s), assuming /24 subnets."""
    addrs: set[str] = set()
    # The default-route address: connecting a UDP socket sends no packets.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))
            addrs.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addrs.add(info[4][0])
    except OSError:
        pass
    nets = {
        ipaddress.ip_network(f"{a}/24", strict=False)
        for a in addrs
        if ipaddress.ip_address(a).is_private and not ipaddress.ip_address(a).is_loopback
    }
    return sorted(nets)


def _port_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _probe(host: str, port: int, timeout: float) -> dict | None:
    if not _port_open(host, port, timeout):
        return None
    try:
        info = EZ1Client(host, port, timeout=3).device_info()
    except EZ1Error:
        return None
    return {"host": host, "port": port, **info}


def scan(networks: list[str] | None = None, port: int = 8050, timeout: float = 0.6) -> list[dict]:
    nets = [ipaddress.ip_network(n, strict=False) for n in networks] if networks else local_networks()
    hosts = [str(h) for net in nets for h in (net.hosts() if net.num_addresses > 1 else [net.network_address])]
    with ThreadPoolExecutor(max_workers=128) as pool:
        results = pool.map(lambda h: _probe(h, port, timeout), hosts)
    return [r for r in results if r]
