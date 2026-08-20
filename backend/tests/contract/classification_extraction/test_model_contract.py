from backend.app.integrations.model.fake import FakeModelGateway
from backend.app.integrations.model.schemas import ExtractionRequest
from backend.app.modules.reviews.results.models import CORE_EXTRACTED_FIELD_KEYS


def test_fake_gateway_returns_the_phase9c_field_contract() -> None:
    result = FakeModelGateway().extract(
        ExtractionRequest(input_text="脱敏合同文本")
    ).output

    assert {field.field_key for field in result.fields} == set(CORE_EXTRACTED_FIELD_KEYS)
    assert len(result.fields) == 7
