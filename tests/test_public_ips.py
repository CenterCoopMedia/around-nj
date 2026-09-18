"""SSRF allowlist for the Around New Jersey snapshot builder."""

import ipaddress

from build_around_nj_demo import ip_is_allowed, is_expected_failure


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


def test_expected_failures_are_source_and_status():
    assert is_expected_failure("https://www.tapinto.net/towns/newark/rss", "http 403")
    assert not is_expected_failure("https://villagegreennj.com/feed/", "http 403")
    assert is_expected_failure(
        "https://www.northjersey.com/arc/outboundfeeds/rss/?outputType=xml", "http 404"
    )
    assert not is_expected_failure(
        "https://www.tapinto.net/towns/newark/rss", "http 404"
    )
