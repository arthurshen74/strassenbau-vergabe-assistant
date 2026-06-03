"""The LANGCHAIN retrieval method: an agentic RAG path over the LangChain vector store.

A different paradigm from the Simple/Plus pipeline (scope -> embed -> hybrid search -> fuse ->
rerank -> answer): here a `create_agent` agent runs a tool-calling loop, deciding when to call a
single `retrieve_context` tool that similarity-searches the `idx-langchain-roadbuilders` index.
There is no multi-query, BM25, or cross-encoder. The chat model and the system prompt are the
latest seeded `project_chat` prompt version -- the prompt with its `{{context}}` evidence block
stripped, since the agent supplies context through the tool rather than via template substitution.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import UUID

from langchain.agents import create_agent
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langchain_core.tools import tool
from langchain_core.utils import convert_to_secret_str
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict

from shared.clients.llm.execution_log import ExecutionLogEvent
from shared.clients.llm.langchain_callback import TelemetryCallbackHandler
from shared.clients.openrouter.usage import UsageEvent
from shared.clients.search.langchain_store import (
    META_PROJECT_UUID,
    META_SOURCE_DOC_TYPE,
    META_SOURCE_DOC_UUID,
    OPENROUTER_BASE_URL,
    build_elasticsearch_client,
    build_langchain_embeddings,
    build_langchain_vector_store,
)
from shared.config import settings

# Passages the retrieve_context tool pulls per call.
RETRIEVE_K = 50

# OpenRouter usage-accounting opt-in; without it the chat response carries no cost.
USAGE_ACCOUNTING_EXTRA_BODY = {"usage": {"include": True}}

# Header that opens the project_chat evidence block; everything from here is dropped for the agent.
_EVIDENCE_HEADER = "Evidence sources:"
_PLACEHOLDER = re.compile(r"{{\s*\w+\s*}}")

# astream_events v2 event names + data keys we relay to SSE.
EV_CHAT_MODEL_STREAM = "on_chat_model_stream"
EV_TOOL_START = "on_tool_start"
EV_TOOL_END = "on_tool_end"
EV_NAME = "name"
EV_DATA = "data"
EV_CHUNK = "chunk"
EV_INPUT = "input"
EV_OUTPUT = "output"
TOOL_ARG_QUERY = "query"
# How much chunk text a LANGCHAIN source carries to the UI (the answer is what's grounded on it).
SOURCE_TEXT_LIMIT = 600

# Transient metadata key holding a retrieved doc's [n] citation number, set when serializing the
# tool result so the answer's [n] citations line up with the sources shown in the UI.
CITE_NUMBER_KEY = "cite_number"


class LangchainSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int
    source_doc_uuid: str | None = None
    source_doc_type: str | None = None
    text: str


class LangchainToken(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str


class LangchainToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str


class LangchainToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[LangchainSource]


# One step of the streamed agent run: an answer token, a retrieval call, or its sources.
LangchainAgentEvent = LangchainToken | LangchainToolCall | LangchainToolResult


def _strip_context_block(system_prompt: str) -> str:
    """Drop the project_chat evidence block and any leftover `{{placeholder}}` tokens."""
    head = re.split(rf"^{_EVIDENCE_HEADER}\s*$", system_prompt, maxsplit=1, flags=re.MULTILINE)[0]
    return _PLACEHOLDER.sub("", head).strip()


class LangchainRetriever:
    """A project-scoped LangChain RAG agent that streams its answer."""

    def __init__(
        self,
        *,
        project_uuid: UUID,
        chat_model: str,
        temperature: float | None,
        system_prompt: str,
        prompt_type: str,
    ) -> None:
        self._client = build_elasticsearch_client()
        vector_store = build_langchain_vector_store(
            build_langchain_embeddings(), self._client
        )
        self._telemetry = TelemetryCallbackHandler(
            project_uuid=project_uuid,
            prompt_type=prompt_type,
            provider_url=OPENROUTER_BASE_URL,
            chat_model=chat_model,
        )
        # Running [n] citation counter for the turn, continued across retrieve calls so every
        # numbered source the model sees stays unique and maps to one row in the UI.
        self._cite_count = 0

        @tool(response_format="content_and_artifact")
        def retrieve_context(query: str) -> tuple[str, list[Document]]:
            """Retrieve relevant passages from the project's documents for a query."""
            docs = vector_store.similarity_search(
                query,
                k=RETRIEVE_K,
                filter=[{"term": {f"metadata.{META_PROJECT_UUID}": str(project_uuid)}}],
            )
            blocks: list[str] = []
            for doc in docs:
                self._cite_count += 1
                doc.metadata[CITE_NUMBER_KEY] = self._cite_count
                blocks.append(f"{_source_label(self._cite_count, doc.metadata)}\n{doc.page_content}")
            return "\n\n".join(blocks), docs

        model = ChatOpenAI(
            model=chat_model,
            base_url=OPENROUTER_BASE_URL,
            api_key=convert_to_secret_str(settings.openrouter_api_key or ""),
            temperature=temperature,
            extra_body=USAGE_ACCOUNTING_EXTRA_BODY,
            callbacks=[self._telemetry],
            streaming=True,
            stream_usage=True,
        )
        self._agent = create_agent(
            model, [retrieve_context], system_prompt=_strip_context_block(system_prompt)
        )

    def stream(self, question: str) -> Iterator[BaseMessage]:
        """Yield the latest message at each step of the agent's tool-calling loop."""
        for state in self._agent.stream(
            {"messages": [{"role": "user", "content": question}]},
            stream_mode="values",
        ):
            yield state["messages"][-1]

    async def astream(self, question: str) -> AsyncIterator[LangchainAgentEvent]:
        """Stream the agent token-by-token on the event loop: answer tokens, the retrieve_context
        call, and its sources. Telemetry is still buffered by the callback and drained afterward."""
        async for event in self._agent.astream_events(
            {"messages": [{"role": "user", "content": question}]},
            version="v2",
        ):
            kind = event.get("event")
            data = event.get(EV_DATA)
            if not isinstance(data, dict):
                continue
            if kind == EV_CHAT_MODEL_STREAM:
                text = _chunk_text(data.get(EV_CHUNK))
                if text:
                    yield LangchainToken(content=text)
            elif kind == EV_TOOL_START:
                tool_input = data.get(EV_INPUT)
                query = tool_input.get(TOOL_ARG_QUERY) if isinstance(tool_input, dict) else None
                if isinstance(query, str):
                    yield LangchainToolCall(query=query)
            elif kind == EV_TOOL_END:
                sources = _tool_sources(data.get(EV_OUTPUT))
                if sources:
                    yield LangchainToolResult(sources=sources)

    def drain_telemetry(self) -> tuple[list[UsageEvent], list[ExecutionLogEvent]]:
        """Return the usage + execution-log events buffered since the last drain, and clear them.

        The agent runs inside a worker thread, so the caller drains here and emits to the DB sinks
        on the main event loop (the engine is bound to that loop)."""
        return self._telemetry.drain()

    def close(self) -> None:
        self._client.close()


def _chunk_text(chunk: Any) -> str:
    """The text of a streamed model chunk. `content` is a str for text models, or a list of
    content blocks for some providers; join the text blocks in that case."""
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part for part in content if isinstance(part, str))
    return ""


def _source_label(number: int, metadata: dict[str, Any]) -> str:
    """A numbered, citation-friendly header. The full source_doc_uuid is shortened so the model
    cites the [n] number (per the project_chat prompt) rather than the raw uuid it would otherwise
    see in the metadata."""
    doc_uuid = str(metadata.get(META_SOURCE_DOC_UUID, ""))
    doc_type = metadata.get(META_SOURCE_DOC_TYPE, "")
    return f"[{number}] {doc_type} (doc {doc_uuid[:8]})"


def _tool_sources(output: Any) -> list[LangchainSource]:
    """The retrieved documents from a finished retrieve_context call. The tool returns
    content_and_artifact, so the ToolMessage carries the `list[Document]` on `.artifact`, each
    tagged with the [n] citation number the model was shown."""
    docs = getattr(output, "artifact", None)
    if not isinstance(docs, list):
        return []
    sources: list[LangchainSource] = []
    for doc in docs:
        if not isinstance(doc, Document):
            continue
        meta = doc.metadata or {}
        number = meta.get(CITE_NUMBER_KEY)
        if not isinstance(number, int):
            continue
        sources.append(
            LangchainSource(
                number=number,
                source_doc_uuid=meta.get(META_SOURCE_DOC_UUID),
                source_doc_type=meta.get(META_SOURCE_DOC_TYPE),
                text=doc.page_content[:SOURCE_TEXT_LIMIT],
            )
        )
    return sources
