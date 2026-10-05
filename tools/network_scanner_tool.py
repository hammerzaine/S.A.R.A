#!/usr/bin/env python3
"""
Network Scanner Tool Module

Provides network discovery and port scanning capabilities for the local network.
Uses ping sweeps to find active hosts and TCP connect scans to identify open ports.

No external dependencies required — uses only Python standard library.

Usage:
    from tools.network_scanner_tool import network_scanner_tool

    # Ping sweep
    result = network_scanner_tool(action="ping_sweep", subnet="192.168.2.0/24")

    # Port scan
    result = network_scanner_tool(action="port_scan", host="192.168.2.103")
"""

import concurrent.futures
import json
import logging
import socket
import subprocess
from typing import Any, Dict, List, Optional

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)

# Common ports to scan
COMMON_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 143, 443, 445,
    993, 995, 1433, 1521, 3306, 3389, 5000, 5432,
    5900, 6379, 8000, 8080, 8081, 8443, 8800, 9000,
    9090, 9200, 11211, 27017, 32400, 11434
]

# Well-known port names
PORT_NAMES = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
    53: "DNS", 80: "HTTP", 110: "POP3", 143: "IMAP",
    443: "HTTPS", 445: "SMB", 993: "IMAPS", 995: "POP3S",
    1433: "MSSQL", 1521: "Oracle", 3306: "MySQL", 3389: "RDP",
    5000: "UPnP", 5432: "PostgreSQL", 5900: "VNC",
    6379: "Redis", 8000: "HTTP-alt", 8080: "HTTP-proxy",
    8081: "HTTP-alt", 8443: "HTTPS-alt", 8800: "SARA-WebUI",
    9000: "HTTP-alt", 9090: "Prometheus", 9200: "Elasticsearch",
    11211: "Memcached", 27017: "MongoDB", 32400: "Plex",
    11434: "Ollama"
}


def _ping_host(ip: str) -> Optional[str]:
    """Ping a single host, return IP if active."""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip],
            capture_output=True,
            timeout=3
        )
        if result.returncode == 0:
            return ip
    except Exception:
        pass
    return None


def _scan_port(ip: str, port: int) -> Optional[Dict[str, Any]]:
    """Check if a single port is open on a host."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex((ip, port))
        sock.close()
        if result == 0:
            return {
                "port": port,
                "name": PORT_NAMES.get(port, "unknown"),
                "state": "open"
            }
    except Exception:
        pass
    return None


def _resolve_hostname(ip: str) -> str:
    """Try to resolve a hostname for an IP."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return "unknown"


def ping_sweep(subnet: str = "192.168.2.0/24") -> Dict[str, Any]:
    """
    Ping sweep a subnet to find active hosts.

    Args:
        subnet: CIDR notation subnet (e.g., "192.168.2.0/24")

    Returns:
        Dict with active hosts, count, and subnet info
    """
    # Parse subnet
    if "/" in subnet:
        base, bits = subnet.split("/")
        bits = int(bits)
    else:
        base = subnet
        bits = 24

    if bits != 24:
        return {"error": "Only /24 subnets are supported for ping sweep"}

    octets = base.split(".")
    if len(octets) != 4:
        return {"error": f"Invalid subnet: {subnet}"}

    prefix = ".".join(octets[:3])
    ips = [f"{prefix}.{i}" for i in range(1, 255)]

    # Ping all hosts in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        results = list(executor.map(_ping_host, ips))

    active = [ip for ip in results if ip]

    # Resolve hostnames
    hosts = []
    for ip in sorted(active, key=lambda x: int(x.split(".")[-1])):
        hostname = _resolve_hostname(ip)
        hosts.append({
            "ip": ip,
            "hostname": hostname
        })

    return {
        "subnet": subnet,
        "active_count": len(hosts),
        "hosts": hosts
    }


def port_scan(host: str, ports: Optional[List[int]] = None) -> Dict[str, Any]:
    """
    Port scan a single host.

    Args:
        host: IP address or hostname to scan
        ports: List of ports to scan (default: COMMON_PORTS)

    Returns:
        Dict with open ports and host info
    """
    if ports is None:
        ports = COMMON_PORTS

    # Resolve hostname if needed
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        return {"error": f"Cannot resolve host: {host}"}

    # Scan ports in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(_scan_port, ip, port): port for port in ports}
        results = []
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    # Sort by port number
    results.sort(key=lambda x: x["port"])

    return {
        "host": host,
        "ip": ip,
        "hostname": _resolve_hostname(ip),
        "open_ports": results,
        "open_count": len(results)
    }


def network_scanner_tool(
    action: str = "ping_sweep",
    subnet: str = "192.168.2.0/24",
    host: str = "",
    ports: Optional[List[int]] = None
) -> str:
    """
    Main entry point for the network scanner tool.

    Args:
        action: "ping_sweep" or "port_scan"
        subnet: Subnet for ping sweep (default: 192.168.2.0/24)
        host: Target host for port scan
        ports: Custom port list for port scan

    Returns:
        JSON string with scan results
    """
    if action == "ping_sweep":
        result = ping_sweep(subnet)
    elif action == "port_scan":
        if not host:
            return json.dumps({"error": "Host is required for port_scan"})
        result = port_scan(host, ports)
    else:
        return json.dumps({"error": f"Unknown action: {action}. Use 'ping_sweep' or 'port_scan'"})

    return json.dumps(result, indent=2)


# --- Schema ---

NETWORK_SCANNER_SCHEMA = {
    "name": "network_scanner",
    "description": (
        "Scan the local network to discover active hosts and open ports. "
        "Use 'ping_sweep' to find all active devices on a subnet, "
        "or 'port_scan' to check which ports are open on a specific host."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["ping_sweep", "port_scan"],
                "description": "Type of scan to perform"
            },
            "subnet": {
                "type": "string",
                "description": "Subnet for ping sweep in CIDR notation (e.g., '192.168.2.0/24')",
                "default": "192.168.2.0/24"
            },
            "host": {
                "type": "string",
                "description": "Target host IP or hostname for port scan"
            },
            "ports": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Custom list of ports to scan (default: common ports)"
            }
        },
        "required": ["action"]
    }
}


# --- Requirements check ---

def check_network_scanner_requirements() -> bool:
    """Check if the network scanner can run."""
    return True  # No external dependencies needed


# --- Registry ---

registry.register(
    name="network_scanner",
    toolset="network",
    schema=NETWORK_SCANNER_SCHEMA,
    handler=lambda args, **kw: network_scanner_tool(
        action=args.get("action", "ping_sweep"),
        subnet=args.get("subnet", "192.168.2.0/24"),
        host=args.get("host", ""),
        ports=args.get("ports")
    ),
    check_fn=check_network_scanner_requirements,
    emoji="🌐",
)
