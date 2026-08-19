import socket
import struct
from collections.abc import Iterator
from pathlib import Path


class AntivirusUnavailableError(RuntimeError):
    pass


class InfectedFileError(RuntimeError):
    pass


class ClamAVScanner:
    def __init__(self, *, host: str, port: int, timeout_seconds: float) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds

    def scan(self, path: Path) -> None:
        try:
            with socket.create_connection(
                (self.host, self.port), timeout=self.timeout_seconds
            ) as connection:
                connection.sendall(b"zINSTREAM\0")
                for chunk in _chunks(path):
                    connection.sendall(struct.pack(">I", len(chunk)))
                    connection.sendall(chunk)
                connection.sendall(struct.pack(">I", 0))
                response = connection.recv(4096)
        except (OSError, TimeoutError) as exc:
            raise AntivirusUnavailableError from exc

        if b"FOUND" in response:
            raise InfectedFileError
        if not response.rstrip(b"\x00\r\n").endswith(b"OK"):
            raise AntivirusUnavailableError


def _chunks(path: Path, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            yield chunk
