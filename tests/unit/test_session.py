from proxy.session import SessionStore

def test_create_session(tmp_path):
    store = SessionStore(tmp_path / "sessions.jsonl")
    session = store.create("reprice west region for Q4")

    assert session.goal == "reprice west region for Q4"
    assert session.status == "open"
    assert session.call_ids == []

def test_append_call_to_session(tmp_path):
    store = SessionStore(tmp_path / "sessions.jsonl")
    session = store.create("test goal")

    store.append_call(session.session_id, "call-1")
    store.append_call(session.session_id, "call-2")

    reloaded = store.get(session.session_id)
    assert reloaded.call_ids == ["call-1", "call-2"]

def test_close_session_records_outcome(tmp_path):
    store = SessionStore(tmp_path / "sessions.jsonl")
    session = store.create("test goal")

    closed = store.close(session.session_id, outcome="success")
    assert closed.status == "closed"
    assert closed.outcome == "success"
    assert closed.closed_at is not None

def test_append_to_unknown_session_raises(tmp_path):
    store = SessionStore(tmp_path / "sessions.jsonl")
    try:
        store.append_call("does not exist", "call-1")
        assert False, "expected KeyError"
    except KeyError:
        pass

def test_store_reloads_state_from_disk(tmp_path):
    path = tmp_path / "sessions.jsonl"
    store1 = SessionStore(path)
    session = store1.create("test goal")
    store1.append_call(session.session_id, "call-1")
    store1.close(session.session_id, outcome="failure")

    store2 = SessionStore(path)
    reloaded = store2.get(session.session_id)
    assert reloaded.call_ids == ["call-1"]
    assert reloaded.status == "closed"
    assert reloaded.outcome == "failure"
