import pytest
from langsmith.run_helpers import get_tracing_context

from citedesk.bootstrap import build_tracer
from citedesk.config import Settings
from citedesk.tracing import Tracer


def test_a_disabled_tracer_does_nothing_and_leaves_clients_alone() -> None:
    tracer = Tracer()
    assert not tracer.enabled
    sentinel = object()
    assert tracer.wrap_openai(sentinel) is sentinel
    with tracer.context({"corpus_version": "1"}):
        assert get_tracing_context().get("enabled") in (None, False)
    tracer.flush()  # must not raise


def test_tracing_is_off_unless_asked_for() -> None:
    assert not build_tracer(Settings()).enabled
    assert not build_tracer(Settings(langsmith_tracing=False, langsmith_api_key="k")).enabled  # type: ignore[arg-type]


def test_tracing_needs_a_key() -> None:
    with pytest.raises(RuntimeError, match="CITEDESK_LANGSMITH_API_KEY"):
        build_tracer(Settings(langsmith_tracing=True))


def test_an_enabled_tracer_labels_the_run_and_tags_it() -> None:
    tracer = build_tracer(
        Settings(
            langsmith_tracing=True,
            langsmith_api_key="lsv2_fake_key_for_the_unit_test",
            langsmith_project="proj",
        )  # type: ignore[arg-type]
    )
    assert tracer.enabled
    with tracer.context({"environment": "test", "model": "m"}):
        context = get_tracing_context()
        assert context["enabled"] is True
        assert context["project_name"] == "proj"
        assert context["metadata"] == {"environment": "test", "model": "m"}
        assert "cite-desk" in context["tags"]


def test_hiding_content_replaces_inputs_and_outputs_in_traces() -> None:
    tracer = build_tracer(
        Settings(
            langsmith_tracing=True,
            langsmith_api_key="lsv2_fake_key_for_the_unit_test",  # type: ignore[arg-type]
            langsmith_hide_content=True,
        )
    )
    client = tracer._client
    assert client is not None
    hidden = client._hide_inputs({"question": "What is the CEO salary?"})  # type: ignore[attr-defined]
    assert "salary" not in str(hidden)


def test_the_api_key_is_not_shown_when_settings_are_printed() -> None:
    settings = Settings(langsmith_api_key="lsv2_secret_value_0123456789")  # type: ignore[arg-type]
    assert "lsv2_secret_value" not in repr(settings)
    assert "lsv2_secret_value" not in settings.model_dump_json()
