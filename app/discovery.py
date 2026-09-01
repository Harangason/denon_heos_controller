from __future__ import annotations

import concurrent.futures
import ipaddress
import socket
from typing import Dict, List


PORTS = (1255, 23, 80, 8080)


def local_ipv4_networks() -> List[ipaddress.IPv4Network]:
    networks = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_loopback or ip.is_link_local:
                continue
            if ip.is_private and not str(ip).startswith("172."):
                networks.append(ipaddress.ip_network(f"{ip}/24", strict=False))
    except Exception:
        pass
    if not networks:
        networks.append(ipaddress.ip_network("192.168.178.0/24"))
    return sorted(set(networks), key=str)


def check_host(ip: str, timeout: float = 0.35) -> Dict[str, object]:
    open_ports = []
    for port in PORTS:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                open_ports.append(port)
        except OSError:
            pass
    score = 0
    if 1255 in open_ports:
        score += 80
    if 23 in open_ports:
        score += 50
    if 80 in open_ports or 8080 in open_ports:
        score += 5
    kind = "Denon/HEOS Kandidat" if score >= 80 else "Netzwerkgeraet"
    return {"ip": ip, "open_ports": open_ports, "score": score, "kind": kind}


def discover_denon_devices() -> Dict[str, object]:
    networks = local_ipv4_networks()
    hosts = [str(host) for network in networks for host in network.hosts()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=96) as pool:
        devices = [result for result in pool.map(check_host, hosts) if result["open_ports"]]
    devices.sort(key=lambda item: (-int(item["score"]), str(item["ip"])))
    return {"ok": True, "networks": [str(network) for network in networks], "devices": devices}
