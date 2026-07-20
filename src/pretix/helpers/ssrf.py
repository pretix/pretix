import ipaddress


_cgnat_net = ipaddress.ip_network('100.64.0.0/10')


def should_block_access(sa):
    ip_addr = ipaddress.ip_address(sa[0])
    check_ip4 = ip_addr.ipv4_mapped if getattr(ip_addr, "ipv4_mapped", None) else ip_addr
    if ip_addr.is_multicast:
        return True, f"Request to multicast address {sa[0]} blocked"
    if ip_addr.is_loopback or ip_addr.is_link_local:
        return True, f"Request to local address {sa[0]} blocked"
    if ip_addr.is_private:
        return True, f"Request to private address {sa[0]} blocked"
    if check_ip4 in _cgnat_net:
        return True, f"Request to RFC 6598 address {sa[0]} blocked"

    return False, None
