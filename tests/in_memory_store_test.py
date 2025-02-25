from typing import Awaitable, Dict

import pytest
import pytest_asyncio

from ilpas.core.store import ValueDict
from ilpas.dx.in_memory_store import InMemoryStore


@pytest.fixture
def store() -> InMemoryStore:
    """Create a fresh InMemoryStore instance."""
    return InMemoryStore()


@pytest_asyncio.fixture
async def populated_store(store: InMemoryStore) -> InMemoryStore:
    """Create a populated InMemoryStore instance."""
    value1: ValueDict = {"user": {"key1": "bar"}, "admin": {"a": False, "b": 42}}
    value2: ValueDict = {"user": {"key1": "foo"}, "admin": {"a": True, "b": 33}}
    value3: ValueDict = {
        "user": {"key2": "baz", "key3": 7},
        "admin": {"base_url": "http://example.com"},
        "callback": {"token": "1234567890"},
    }
    await store.put_by_primary_key(
        value1,
        {"guid": "slack", "user_id": "123"},
        namespace="default",
        primary_key="1",
    )
    await store.put_by_primary_key(
        value2,
        {"guid": "slack", "user_id": "456"},
        namespace="default",
        primary_key="2",
    )
    await store.put_by_primary_key(
        value3,
        {"guid": "github", "user_id": "123"},
        namespace="default",
        primary_key="3",
    )
    return store


@pytest_asyncio.fixture
async def multi_namespace_store(
    store: InMemoryStore,
) -> tuple[InMemoryStore, str, str, str]:
    """Create a populated InMemoryStore instance."""
    value1: ValueDict = {"user": {"key1": "bar"}, "admin": {"a": False, "b": 42}}
    value2: ValueDict = {"user": {"key1": "foo"}, "admin": {"a": True, "b": 33}}
    value3: ValueDict = {
        "user": {"key2": "baz", "key3": 7},
        "admin": {"base_url": "http://example.com"},
        "callback": {"token": "1234567890"},
    }
    pkey1 = await store.put_by_labels(
        value1, {"guid": "slack", "user_id": "123"}, namespace="ns1"
    )
    pkey2 = await store.put_by_labels(
        value2, {"guid": "slack", "user_id": "456"}, namespace="ns2"
    )
    pkey3 = await store.put_by_labels(
        value3, {"guid": "github", "user_id": "123"}, namespace="ns1"
    )
    return store, pkey1, pkey2, pkey3


@pytest.mark.asyncio
async def test_find_primary_keys_by_labels(populated_store: InMemoryStore):
    """Test finding primary keys by labels."""
    keys = await populated_store._find_primary_keys_by_labels(
        namespace="default", labels={"guid": "slack"}
    )
    assert keys == {"1", "2"}


@pytest.mark.asyncio
async def test_put_by_primary_key(store: InMemoryStore):
    """Test storing a value with labels."""
    value: ValueDict = {"user": {"key1": "bar"}, "admin": {"a": False, "b": 42}}
    primary_key = await store.put_by_primary_key(
        value, {"guid": "slack", "user_id": "123"}, namespace="default", primary_key="1"
    )
    result = await store.get_by_primary_key(primary_key, namespace="default")
    result2 = await store.get_by_labels(
        {"guid": "slack", "user_id": "123"}, namespace="default"
    )
    assert result["value"] == result2["value"] == value
    assert result["labels"] == result2["labels"] == {"guid": "slack", "user_id": "123"}
    assert result["primary_key"] == result2["primary_key"] == "1"


@pytest.mark.asyncio
async def test_put_by_labels(store: InMemoryStore):
    """Test storing a value without specifying a primary key."""
    value: ValueDict = {"user": {"key1": "bar"}, "admin": {"a": False, "b": 42}}
    primary_key = await store.put_by_labels(
        value, {"guid": "slack", "user_id": "123"}, namespace="default"
    )
    assert primary_key is not None
    result = await store.get_by_primary_key(primary_key, namespace="default")
    result2 = await store.get_by_labels(
        {"guid": "slack", "user_id": "123"}, namespace="default"
    )
    assert result["value"] == result2["value"] == value
    assert result["labels"] == result2["labels"] == {"guid": "slack", "user_id": "123"}


@pytest.mark.asyncio
async def test_put_without_namespace(store: InMemoryStore):
    """Test storing a value without specifying a namespace."""
    value: ValueDict = {"user": {"key1": "bar"}, "admin": {"a": False, "b": 42}}
    primary_key = await store.put_by_labels(
        value, labels={"guid": "slack", "user_id": "123"}
    )
    assert primary_key is not None
    result = await store.get_by_primary_key(primary_key)
    result2 = await store.get_by_labels({"guid": "slack", "user_id": "123"})
    assert result["value"] == result2["value"] == value
    assert result["labels"] == result2["labels"] == {"guid": "slack", "user_id": "123"}


@pytest.mark.asyncio
async def test_put_without_labels(store: InMemoryStore):
    """Test storing a value without specifying labels."""
    value: ValueDict = {"user": {"key1": "bar"}, "admin": {"a": False, "b": 42}}
    primary_key = await store.put_by_labels(value, {})
    result = await store.get_by_primary_key(primary_key)
    result2 = await store.get_by_labels({})
    assert result["value"] == result2["value"] == value
    assert result["labels"] == result2["labels"] == {}
