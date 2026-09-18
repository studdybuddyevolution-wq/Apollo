import socket

import pytest
import requests

import source_ingestion


def test_download_uses_validated_ip_when_dns_rebinds(monkeypatch):
    validation_ip = "93.184.216.34"
    rebound_private_ip = "127.0.0.1"
    dns_calls: list[str] = []
    connection_targets: list[tuple[str, int]] = []

    def fake_getaddrinfo(host, port, *args, **kwargs):
        dns_calls.append(host)
        address = validation_ip if len(dns_calls) == 1 else rebound_private_ip
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    def fake_create_connection(address, *args, **kwargs):
        connection_targets.append(address)
        raise OSError("simulated connection failure")

    monkeypatch.setattr(source_ingestion.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(source_ingestion.urllib3_connection, "create_connection", fake_create_connection)

    safe_ip, safe_url = source_ingestion._validate_public_url(
        "http://rebind.example.test/resource"
    )
    assert safe_ip == validation_ip

    adapter = source_ingestion._PinnedIPAdapter(safe_ip)
    with requests.Session() as session:
        session.trust_env = False
        session.mount("http://", adapter)
        with pytest.raises(requests.exceptions.ConnectionError):
            session.get(
                safe_url,
                timeout=source_ingestion.REQUEST_TIMEOUT,
                allow_redirects=False,
                stream=True,
            )

    assert connection_targets == [(validation_ip, 80)]
    assert dns_calls == ["rebind.example.test"]
    assert rebound_private_ip not in [host for host, _ in connection_targets]
