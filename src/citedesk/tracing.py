"""Optional tracing of every answer in LangSmith.

A trace shows each step of one question (retrieve, write, verify) with timings, so a wrong or slow
answer can be inspected afterwards. It is OFF by default because a trace contains the question and,
unless content is hidden, the handbook passages sent to the model: that leaves this system for a
third party. Turn it on with CITEDESK_LANGSMITH_TRACING=true, and hide the text with
CITEDESK_LANGSMITH_HIDE_CONTENT=true if the documents are sensitive.

Tracing never changes an answer, and a LangSmith outage only loses traces.
"""

import contextlib
from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Any

from langsmith import Client
from langsmith.run_helpers import tracing_context


class Tracer:
    def __init__(self, client: Client | None = None, project: str = "cite-desk") -> None:
        self._client = client
        self._project = project

    @property
    def enabled(self) -> bool:
        return self._client is not None

    @classmethod
    def create(cls, api_key: str, project: str, *, hide_content: bool) -> "Tracer":
        def blank(_: Mapping[str, Any]) -> dict[str, Any]:
            return {"hidden": "content is hidden by CITEDESK_LANGSMITH_HIDE_CONTENT"}

        client = Client(
            api_key=api_key,
            hide_inputs=blank if hide_content else None,
            hide_outputs=blank if hide_content else None,
        )
        return cls(client, project)

    def context(self, metadata: Mapping[str, str]) -> AbstractContextManager[Any]:
        """Everything run inside this context is traced. A no-op when tracing is off."""
        if self._client is None:
            return contextlib.nullcontext()
        return tracing_context(
            enabled=True,
            client=self._client,
            project_name=self._project,
            metadata=dict(metadata),
            tags=["cite-desk"],
        )

    def wrap_openai(self, client: Any) -> Any:
        """Make calls through an OpenAI client appear (with token counts) inside the trace."""
        if self._client is None:
            return client
        from langsmith.wrappers import wrap_openai  # imported only when tracing is on

        return wrap_openai(client)

    def flush(self) -> None:
        """Send any traces still waiting. Needed before a short-lived command exits."""
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.flush()
