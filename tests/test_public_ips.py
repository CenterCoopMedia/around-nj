"""SSRF allowlist for the Around New Jersey snapshot builder."""

import ipaddress

from build_around_nj_demo import ip_is_allowed


def test_loopback_and_rfc1918_are_blocked():
    assert not ip_is_allowed(ipaddress.ip_address("127.0.0.1"))
    assert not ip_is_allowed(ipaddress.ip_address("10.0.0.1"))
    assert not ip_is_allowed(ipaddress.ip_address("192.168.1.1"))


def test_tailscale_cgnat_is_blocked():
    assert not ip_is_allowed(ipaddress.ip_address("100.64.0.1"))
    assert not ip_is_allowed(ipaddress.ip_address("100.127.255.254"))


def test_public_unicast_is_allowed():
    assert ip_is_allowed(ipaddress.ip_address("1.1.1.1"))
    assert ip_is_allowed(ipaddress.ip_address("8.8.8.8"))


def test_multicast_is_blocked():
    assert not ip_is_allowed(ipaddress.ip_address("224.0.0.1"))
    assert not ip_is_allowed(ipaddress.ip_address("ff02::1"))
