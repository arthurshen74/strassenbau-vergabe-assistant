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
from collections.abc import Iterator
from uuid import UUID

from langchain.agents import create_agent
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langchain_core.tools import tool
from langchain_core.utils import convert_to_secret_str
from langchain_openai import ChatOpenAI

from shared.clients.search.langchain_store import (
    META_PROJECT_UUID,
    OPENROUTER_BASE_URL,
    build_elasticsearch_client,
    build_langchain_embeddings,
    build_langchain_vector_store,
)
from shared.config import settings

# Passages the retrieve_context tool pulls per call.
RETRIEVE_K = 50

# Header that opens the project_chat evidence block; everything from here is dropped for the agent.
_EVIDENCE_HEADER = "Evidence sources:"
_PLACEHOLDER = re.compile(r"{{\s*\w+\s*}}")


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
    ) -> None:
        self._client = build_elasticsearch_client()
        vector_store = build_langchain_vector_store(
            build_langchain_embeddings(), self._client
        )

        @tool(response_format="content_and_artifact")
        def retrieve_context(query: str) -> tuple[str, list[Document]]:
            """Retrieve relevant passages from the project's documents for a query."""
            docs = vector_store.similarity_search(
                query,
                k=RETRIEVE_K,
                filter=[{"term": {f"metadata.{META_PROJECT_UUID}": str(project_uuid)}}],
            )
            serialized = "\n\n".join(
                f"Source: {doc.metadata}\nContent: {doc.page_content}" for doc in docs
            )
            return serialized, docs

        model = ChatOpenAI(
            model=chat_model,
            base_url=OPENROUTER_BASE_URL,
            api_key=convert_to_secret_str(settings.openrouter_api_key or ""),
            temperature=temperature,
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

    def close(self) -> None:
        self._client.close()
