"""Generate a short title for a conversation from its first user message.

Single-shot, free-form `conversation_name` prompt: the first user turn goes in, a short title
comes back, and it is persisted as the conversation's `title`. Returns None when the conversation
has no user message yet (nothing to name).
"""

from __future__ import annotations

from uuid import UUID

from shared.models.chat_message import ChatMessage
from shared.models.conversation import Conversation
from shared.models.enums import MessageKind, PromptType
from shared.repositories.conversations import ConversationRepository
from shared.repositories.messages import MessageRepository
from shared.services.prompt_runner import PromptRunner


class ConversationNamingService:
    def __init__(
        self,
        runner: PromptRunner,
        conversations: ConversationRepository,
        messages: MessageRepository,
    ) -> None:
        self._runner = runner
        self._conversations = conversations
        self._messages = messages

    async def name_from_first_message(self, conversation_uuid: UUID) -> Conversation | None:
        history = await self._messages.list_for_conversation(conversation_uuid)
        first_user = next(
            (m for m in history if m.kind == MessageKind.USER and m.content), None
        )
        if first_user is None or first_user.content is None:
            return None
        raw = await self._runner.run_text(
            PromptType.CONVERSATION_NAME,
            messages=[ChatMessage(role="user", content=first_user.content)],
        )
        title = raw.strip().strip("\"'").strip()
        if not title:
            return None
        return await self._conversations.set_title(conversation_uuid, title)
