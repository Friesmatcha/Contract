from fastapi.testclient import TestClient


def test_review_results_openapi_projects_phase9c_contract(auth_client: TestClient) -> None:
    openapi = auth_client.app.openapi()
    paths = openapi["paths"]
    get_results = paths["/api/v1/review-tasks/{review_task_id}/results"]["get"]

    assert get_results["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/ReviewResultsResponse"
    )
    assert {parameter["name"] for parameter in get_results["parameters"]} >= {
        "X-Support-Access-Grant",
        "risk_severity",
        "risk_status",
        "clause_status",
        "include_evidence",
    }
    assert get_results["responses"]["409"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/ErrorResponse"
    )
    assert "source_span_id" in openapi["components"]["schemas"]["SourceLocatorResponse"][
        "properties"
    ]
