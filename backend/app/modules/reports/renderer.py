from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

TEMPLATE_VERSION = "report-v1"


class ReportRendererError(RuntimeError):
    def __init__(self, code: str, message: str = "报告渲染失败。") -> None:
        self.code = code
        super().__init__(message)


class ReportRenderer(Protocol):
    def available(self, format: str) -> bool: ...

    def render_pdf(self, html: str) -> bytes: ...


def render_html(snapshot: dict[str, object]) -> str:
    template_dir = Path(__file__).with_name("templates")
    environment = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
    )
    return str(environment.get_template(f"{TEMPLATE_VERSION}.html").render(snapshot=snapshot))


class FakeReportRenderer:
    def available(self, format: str) -> bool:
        return format in {"html", "pdf"}

    def render_pdf(self, html: str) -> bytes:
        return b"%PDF-FAKE-1.0\n" + html.encode("utf-8")


class ChromiumPdfRenderer:
    """Fixed, shell-free Chromium CLI boundary used only by the report worker."""

    _commands = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")

    def __init__(self, *, timeout_seconds: int = 60) -> None:
        self.timeout_seconds = timeout_seconds

    def _command(self) -> str | None:
        return next((command for command in self._commands if shutil.which(command)), None)

    def available(self, format: str) -> bool:
        return format == "html" or self._command() is not None

    def render_pdf(self, html: str) -> bytes:
        command = self._command()
        if command is None:
            raise ReportRendererError(
                "REPORT_RENDERER_UNAVAILABLE", "Chromium renderer unavailable."
            )
        with tempfile.TemporaryDirectory(prefix="report-render-") as directory:
            root = Path(directory)
            html_path = root / "report.html"
            output_path = root / "report.pdf"
            profile_path = root / "profile"
            html_path.write_text(html, encoding="utf-8")
            try:
                subprocess.run(
                    [
                        command,
                        "--headless",
                        "--no-sandbox",
                        "--disable-gpu",
                        "--disable-dev-shm-usage",
                        "--disable-extensions",
                        "--disable-background-networking",
                        "--no-first-run",
                        "--no-default-browser-check",
                        f"--user-data-dir={profile_path}",
                        f"--print-to-pdf={output_path}",
                        html_path.as_uri(),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                )
            except FileNotFoundError as exc:
                raise ReportRendererError("REPORT_RENDERER_UNAVAILABLE") from exc
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                raise ReportRendererError("REPORT_RENDER_FAILED") from exc
            try:
                return output_path.read_bytes()
            except OSError as exc:
                raise ReportRendererError("REPORT_RENDER_FAILED") from exc


__all__ = [
    "ChromiumPdfRenderer",
    "FakeReportRenderer",
    "ReportRenderer",
    "ReportRendererError",
    "TEMPLATE_VERSION",
    "render_html",
]
