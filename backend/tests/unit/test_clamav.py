from pathlib import Path
from unittest.mock import patch

from backend.app.integrations.antivirus.clamav import ClamAVScanner


class FakeConnection:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.sent: list[bytes] = []

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def sendall(self, payload: bytes) -> None:
        self.sent.append(payload)

    def recv(self, _size: int) -> bytes:
        return self.response


def test_clamav_accepts_nul_terminated_clean_response(tmp_path: Path) -> None:
    sample = tmp_path / "sample.pdf"
    sample.write_bytes(b"%PDF-1.7\n%%EOF")
    connection = FakeConnection(b"stream: OK\x00")

    with patch(
        "backend.app.integrations.antivirus.clamav.socket.create_connection",
        return_value=connection,
    ):
        ClamAVScanner(host="clamav", port=3310, timeout_seconds=1).scan(sample)

    assert connection.sent[0] == b"zINSTREAM\x00"
    assert connection.sent[-1] == b"\x00\x00\x00\x00"
