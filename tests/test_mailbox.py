"""Unit tests for MailboxQueue."""

from __future__ import annotations

import asyncio

import pytest

from agentlens.server.mailbox import MailboxQueue, MailboxResponse


@pytest.mark.asyncio
async def test_enqueue_creates_pending_entry() -> None:
    # Arrange
    queue = MailboxQueue(timeout=5.0)
    messages = [{"role": "user", "content": "hello"}]

    # Act
    entry = queue.enqueue(messages, "gpt-4o", [])

    # Assert
    pending = queue.list_pending()
    assert len(pending) == 1
    assert pending[0].request_id == entry.request_id
    assert pending[0].model == "gpt-4o"
    assert pending[0].messages == messages


@pytest.mark.asyncio
async def test_submit_response_unblocks_waiter() -> None:
    queue = MailboxQueue(timeout=5.0)
    entry = queue.enqueue([{"role": "user", "content": "hi"}], "test", [])
    task = asyncio.create_task(queue.wait_for_response(entry.request_id))
    await asyncio.sleep(0.01)  # let the waiter start
    queue.submit_response(entry.request_id, MailboxResponse(content="hello"))
    result = await task
    assert result.content == "hello"


@pytest.mark.asyncio
async def test_wait_timeout_raises() -> None:
    # Arrange
    queue = MailboxQueue(timeout=0.05)
    entry = queue.enqueue([{"role": "user", "content": "slow"}], "gpt-4o", [])

    # Act & Assert
    with pytest.raises(TimeoutError):
        await queue.wait_for_response(entry.request_id)


@pytest.mark.asyncio
async def test_submit_unknown_id_raises() -> None:
    # Arrange
    queue = MailboxQueue(timeout=5.0)

    # Act & Assert
    with pytest.raises(ValueError, match="Unknown request ID"):
        queue.submit_response(999, MailboxResponse(content="orphan"))


@pytest.mark.asyncio
async def test_stats_reflects_state() -> None:
    # Arrange
    queue = MailboxQueue(timeout=5.0)
    entry1 = queue.enqueue([{"role": "user", "content": "first"}], "gpt-4o", [])
    entry2 = queue.enqueue([{"role": "user", "content": "second"}], "gpt-4o", [])

    # Act — serve one of the two
    task = asyncio.create_task(queue.wait_for_response(entry1.request_id))
    await asyncio.sleep(0.01)
    queue.submit_response(entry1.request_id, MailboxResponse(content="done"))
    await task

    # Assert
    stats = queue.stats()
    assert stats["pending"] == 1
    assert stats["served"] == 1
    assert stats["timeout"] == 5.0
    _ = entry2  # referenced to silence unused-variable warning


@pytest.mark.asyncio
async def test_get_entry_returns_none_for_unknown() -> None:
    # Arrange
    queue = MailboxQueue(timeout=5.0)

    # Act & Assert
    assert queue.get_entry(404) is None


@pytest.mark.asyncio
async def test_list_pending_excludes_served() -> None:
    # Arrange
    queue = MailboxQueue(timeout=5.0)
    entry = queue.enqueue([{"role": "user", "content": "transient"}], "gpt-4o", [])

    # Act — complete the request
    task = asyncio.create_task(queue.wait_for_response(entry.request_id))
    await asyncio.sleep(0.01)
    queue.submit_response(entry.request_id, MailboxResponse(content="done"))
    await task

    # Assert
    assert queue.list_pending() == []
    assert queue.get_entry(entry.request_id) is None
