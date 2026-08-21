from backend.app.modules.reports.renderer import FakeReportRenderer, render_html


def _snapshot() -> dict[str, object]:
    return {
        "contract": {"title": "<script>alert(1)</script>", "display_no": "C-1"},
        "organization": {"name": "Org", "report_watermark": "W"},
        "file": {"original_name": "f.pdf", "version_no": 1},
        "review_task": {"display_no": "R-1", "status": "completed"},
        "report": {"display_no": "P-1", "template_version": "report-v1"},
        "results": {
            "summary": {
                "risk_total": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "warning_total": 0,
                "unresolved_count": 0,
                "required_manual_count": 0,
            },
            "classification": {
                "model_value": "purchase",
                "current_value": "purchase",
                "status": "detected",
                "confidence": 1,
            },
            "extracted_fields": [],
            "risk_findings": [],
            "clause_comparisons": [],
        },
        "disclaimer": "<unsafe>",
        "human_review": {"revisions": []},
    }


def test_report_template_escapes_untrusted_text_and_sets_csp() -> None:
    html = render_html(_snapshot())

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "default-src 'none'" in html


def test_fake_pdf_renderer_is_deterministic_for_automated_tests() -> None:
    html = render_html(_snapshot())
    output = FakeReportRenderer().render_pdf(html)

    assert output.startswith(b"%PDF-FAKE-1.0\n")
    assert output.endswith(html.encode("utf-8"))
