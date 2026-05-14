from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncIterator
from uuid import uuid4

from api.services.citation_verifier import CitationVerifier
from api.services.llm_client import LLMClient
from api.services.retrieval_orchestrator import RetrievedChunk, RetrievalOrchestrator, SourceType

SYSTEM_PROMPT = """You are Junas, a legal research assistant. You answer legal questions using ONLY the provided source materials.

Rules:
1. Use only the supplied source excerpts.
2. Cite legal claims with source ids in square brackets, e.g., [ORS 685.010].
3. If information is missing from sources, explicitly say what is missing.
4. Do not provide legal advice; describe what the sources state.
5. If jurisdiction/topic is out of scope, say so clearly.
"""


def assemble_context(chunks: list[RetrievedChunk]) -> str:
    parts: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        header = f"[Source {index}: {chunk.source_id}]"
        if chunk.source_type == SourceType.STATUTE:
            header += f" (Oregon Statute, {chunk.metadata.get('name', '')})"
        elif chunk.source_type == SourceType.GLOSSARY:
            header += f" ({chunk.metadata.get('jurisdiction', '')} Glossary)"
        elif chunk.source_type == SourceType.CASE_LAW:
            header += f" (Case: {chunk.metadata.get('case_name', '')})"
        elif chunk.source_type == SourceType.TREATY:
            header += f" (Rome Statute Article {chunk.metadata.get('article_number', '')})"
        parts.append(f"{header}\n{chunk.text}")
    return "\n\n---\n\n".join(parts)


def build_prompt(
    query: str,
    context: str,
    conversation_history: list[dict[str, str]] | None = None,
    max_history_messages: int = 6,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if conversation_history:
        trimmed = conversation_history[-max_history_messages:]
        messages.extend(trimmed)

    user_prompt = (
        "Based on the following legal sources, answer this question.\n\n"
        f"Question: {query}\n\n"
        f"Sources:\n\n{context}\n\n"
        "Provide a concise answer with citations."
    )
    messages.append({"role": "user", "content": user_prompt})
    return messages


class ConversationStore:
    def __init__(self, pg_pool: Any | None):
        self.pg_pool = pg_pool
        self._memory: dict[str, list[dict[str, Any]]] = {}

    @asynccontextmanager
    async def _acquire(self) -> AsyncIterator[Any]:
        if self.pg_pool is None:
            yield None
            return
        async with self.pg_pool.acquire() as connection:
            yield connection

    async def create_conversation(self) -> str:
        if self.pg_pool is None:
            conversation_id = str(uuid4())
            self._memory[conversation_id] = []
            return conversation_id

        async with self._acquire() as connection:
            conversation_id = await connection.fetchval("INSERT INTO conversations DEFAULT VALUES RETURNING id")
        return str(conversation_id)

    async def append_turn(
        self,
        conversation_id: str,
        role: str,
        content: str,
        sources: list[dict[str, Any]] | None = None,
        citations: dict[str, Any] | None = None,
    ) -> None:
        if self.pg_pool is None:
            turns = self._memory.setdefault(conversation_id, [])
            turns.append(
                {
                    "role": role,
                    "content": content,
                    "sources": sources,
                    "citations": citations,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            return

        async with self._acquire() as connection:
            await connection.execute(
                """
                INSERT INTO conversation_turns(conversation_id, role, content, sources, citations)
                VALUES($1::uuid, $2, $3, $4::jsonb, $5::jsonb)
                """,
                conversation_id,
                role,
                content,
                sources,
                citations,
            )
            await connection.execute(
                "UPDATE conversations SET updated_at = NOW() WHERE id = $1::uuid",
                conversation_id,
            )

    async def get_conversation(self, conversation_id: str) -> list[dict[str, Any]] | None:
        if self.pg_pool is None:
            if conversation_id not in self._memory:
                return None
            return list(self._memory[conversation_id])

        async with self._acquire() as connection:
            exists = await connection.fetchval(
                "SELECT id FROM conversations WHERE id = $1::uuid LIMIT 1",
                conversation_id,
            )
            if exists is None:
                return None

            rows = await connection.fetch(
                """
                SELECT role, content, sources, citations, created_at
                FROM conversation_turns
                WHERE conversation_id = $1::uuid
                ORDER BY created_at ASC
                """,
                conversation_id,
            )

        return [
            {
                "role": row["role"],
                "content": row["content"],
                "sources": row["sources"],
                "citations": row["citations"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]

    async def delete_conversation(self, conversation_id: str) -> bool:
        if self.pg_pool is None:
            return self._memory.pop(conversation_id, None) is not None

        async with self._acquire() as connection:
            status = await connection.execute(
                "DELETE FROM conversations WHERE id = $1::uuid",
                conversation_id,
            )
        return status.endswith("1")


class LegalQAService:
    def __init__(
        self,
        orchestrator: RetrievalOrchestrator,
        llm_client: LLMClient,
        citation_verifier: CitationVerifier,
        conversation_store: ConversationStore,
    ):
        self.orchestrator = orchestrator
        self.llm = llm_client
        self.verifier = citation_verifier
        self.conversations = conversation_store

    async def answer(
        self,
        question: str,
        sources: list[SourceType] | None = None,
        conversation_id: str | None = None,
        top_k: int = 8,
    ) -> dict[str, Any]:
        if conversation_id is None:
            conversation_id = await self.conversations.create_conversation()
            history_rows: list[dict[str, Any]] = []
        else:
            existing = await self.conversations.get_conversation(conversation_id)
            if existing is None:
                raise ValueError("Conversation not found")
            history_rows = existing

        history_messages = [
            {"role": str(row["role"]), "content": str(row["content"])}
            for row in history_rows
            if row.get("role") in {"user", "assistant"}
        ]

        chunks = await self.orchestrator.retrieve(question, sources=sources, top_k=top_k)
        context = assemble_context(chunks)
        prompt_messages = build_prompt(question, context, conversation_history=history_messages)
        answer_text = await self.llm.generate(prompt_messages, max_tokens=1500)
        citation_report = await self.verifier.extract_and_verify(answer_text, chunks)

        source_rows = [
            {
                "source_id": chunk.source_id,
                "source_type": chunk.source_type.value,
                "text_snippet": chunk.text[:400],
                "metadata": chunk.metadata,
                "relevance_score": float(chunk.score),
            }
            for chunk in chunks
        ]

        await self.conversations.append_turn(conversation_id, "user", question)
        await self.conversations.append_turn(
            conversation_id,
            "assistant",
            answer_text,
            sources=source_rows,
            citations=citation_report,
        )

        return {
            "answer": answer_text,
            "sources": source_rows,
            "citations": citation_report,
            "conversation_id": conversation_id,
        }

    async def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        turns = await self.conversations.get_conversation(conversation_id)
        if turns is None:
            return None
        return {
            "conversation_id": conversation_id,
            "turns": turns,
        }

    async def delete_conversation(self, conversation_id: str) -> bool:
        return await self.conversations.delete_conversation(conversation_id)
