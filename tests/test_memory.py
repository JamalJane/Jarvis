import pytest
from jarvis.memory.pinecone_store import PineconeStore, ActionRecord
from jarvis.memory.prediction import PredictionEngine
from jarvis.memory.context_selector import ContextSelector


def test_pinecone_store_initializes_without_key():
    store = PineconeStore(api_key="fake-key-for-test")
    assert len(store.fallback_store) == 0


def test_pinecone_store_get_stats():
    store = PineconeStore()
    stats = store.get_stats()
    assert "total_stored" in stats
    assert "pinecone_connected" in stats
    assert stats["total_stored"] == 0


def test_store_action():
    store = PineconeStore(api_key="fake-key-for-tests")
    record = ActionRecord(
        action_type="click",
        action_target="button",
        success=True
    )
    store.store_action(record)
    assert len(store.fallback_store) == 1


def test_query_similar():
    store = PineconeStore(api_key="fake-key-for-tests")
    record1 = ActionRecord(action_type="click", action_target="btn1", success=True)
    record2 = ActionRecord(action_type="click", action_target="btn2", success=True)
    store.store_action(record1)
    store.store_action(record2)

    results = store.query_similar("click")
    assert len(results) >= 1


def test_prediction_engine_initializes():
    store = PineconeStore()
    engine = PredictionEngine(store)
    assert engine.store is not None


def test_prediction_engine_predict_outcome_no_data():
    store = PineconeStore(api_key="fake-key-for-tests")
    engine = PredictionEngine(store)
    result = engine.predict_outcome("click", "unknown_target_xyz_12345")
    assert result is None


def test_prediction_engine_update_confidence():
    store = PineconeStore()
    engine = PredictionEngine(store)
    engine.update_confidence("click", "test", True)
    engine.update_confidence("click", "test", True)
    engine.update_confidence("click", "test", False)

    conf = engine.get_confidence("click", "test")
    assert conf == 2/3


def test_context_selector_initializes():
    selector = ContextSelector()
    assert selector.phase == "hybrid"


def test_context_selector_web():
    selector = ContextSelector()
    assert selector.select_context("web") in ["dom", "hybrid"]


def test_context_selector_os():
    selector = ContextSelector()
    assert selector.select_context("os") == "screenshot"


def test_context_selector_should_use_screenshot():
    selector = ContextSelector()
    assert selector.should_use_screenshot("click", 0.9) is False
    assert selector.should_use_screenshot("click", 0.5) is True
