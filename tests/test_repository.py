import sys
print(sys.path)

import os
import tempfile

from service.storage.sqlite import init_db
from service.conversation.repository import ConversationRepository


def test_conversation_lifecycle():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name

    try:
        init_db(db_path)

        repo = ConversationRepository(db_path=db_path)

        # Create conversation
        conversation_id = repo.create_conversation()
        assert repo.conversation_exists(conversation_id)

        # Add messages
        repo.add_message(conversation_id, "user", "Hello")
        repo.add_message(conversation_id, "assistant", "Hi there")

        messages = repo.get_messages(conversation_id)

        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hi there"

    finally:
        os.remove(db_path)

