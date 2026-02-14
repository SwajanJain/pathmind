import ipaddress


def anonymize_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    value = ip.strip()
    if not value:
        return None
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return None

    if isinstance(parsed, ipaddress.IPv4Address):
        octets = value.split(".")
        if len(octets) != 4:
            return None
        octets[-1] = "0"
        return ".".join(octets)

    hextets = parsed.exploded.split(":")
    masked = hextets[:4] + ["0000", "0000", "0000", "0000"]
    return ":".join(masked)
