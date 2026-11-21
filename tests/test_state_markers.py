"""Ambiguous state claims never authorize deletion, reuse or copying."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from desktop_django_starter import app_state, state_staging


def snapshot(root: Path):
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def duplicate_claim(record, key, escaped, conflicting):
    # Put a wrong claim first: permissive last-member-wins parsing accepts it.
    encoded_key = json.dumps(key)
    if escaped:
        encoded_key = f'"\\u{ord(key[0]):04x}{key[1:]}"'
    value = "foreign-claim" if conflicting else record[key]
    return "{" + encoded_key + ":" + json.dumps(value) + "," + json.dumps(record)[1:]


@pytest.mark.parametrize("key", ["schema", "stage", "kind"])
@pytest.mark.parametrize("escaped", [False, True], ids=["literal", "escaped"])
@pytest.mark.parametrize("conflicting", [False, True], ids=["equal", "conflicting"])
def test_duplicate_owner_claim_retains_entire_stage(tmp_path, caplog, key, escaped, conflicting):
    app_state.prepare_versioned_state(tmp_path, "1.0.0")
    stage = tmp_path / "state" / (".dds-stage-" + "a" * 32)
    stage.mkdir()
    owner = {"schema": 1, "stage": stage.name, "kind": "dds-state-initialization"}
    (stage / ".stage-owner.json").write_text(duplicate_claim(owner, key, escaped, conflicting))
    (stage / "media").mkdir()
    (stage / "media" / "sentinel").write_bytes(b"synthetic retained media")
    before = snapshot(stage)

    app_state.prepare_versioned_state(tmp_path, "2.0.0")

    assert stage.is_dir()
    assert snapshot(stage) == before
    assert "Retained" in caplog.text
    assert len(caplog.text) < 1000


@pytest.mark.parametrize("key", ["version", "copied_from", "created_at"])
@pytest.mark.parametrize("escaped", [False, True], ids=["literal", "escaped"])
@pytest.mark.parametrize("conflicting", [False, True], ids=["equal", "conflicting"])
@pytest.mark.parametrize("use", ["reopen", "predecessor"])
def test_duplicate_completion_claim_refuses_without_changing_state(
    tmp_path, key, escaped, conflicting, use
):
    state = app_state.prepare_versioned_state(tmp_path, "1.0.0")
    with sqlite3.connect(state / "app.sqlite3") as db:
        db.execute("CREATE TABLE synthetic (value TEXT)")
    marker = state / "state.json"
    marker.write_text(duplicate_claim(json.loads(marker.read_text()), key, escaped, conflicting))
    before = snapshot(state)

    with pytest.raises(ImproperlyConfigured, match="completion marker"):
        app_state.prepare_versioned_state(tmp_path, "1.0.0" if use == "reopen" else "2.0.0")

    assert snapshot(state) == before
    assert not (tmp_path / "state" / "2.0.0").exists()
    assert list((tmp_path / "state").glob(".dds-stage-*")) == []


@pytest.mark.parametrize(
    "extra",
    ['{"claim":0,"claim":1}', '{"claim":0,"cl\\u0061im":1}', '[{"key":1,"key":1}]'],
)
def test_nested_duplicate_completion_members_refuse(tmp_path, extra):
    state = app_state.prepare_versioned_state(tmp_path, "1.0.0")
    marker = state / "state.json"
    marker.write_text('{"extra":' + extra + "," + marker.read_text()[1:])
    before = snapshot(state)
    with pytest.raises(ImproperlyConfigured, match="completion marker"):
        app_state.prepare_versioned_state(tmp_path, "1.0.0")
    assert snapshot(state) == before


def test_ordinary_owned_abandoned_stage_is_still_recovered(tmp_path):
    app_state.prepare_versioned_state(tmp_path, "1.0.0")
    stage = tmp_path / "state" / (".dds-stage-" + "b" * 32)
    stage.mkdir()
    (stage / ".stage-owner.json").write_text(
        json.dumps({"schema": 1, "stage": stage.name, "kind": "dds-state-initialization"})
    )
    (stage / "media").mkdir()
    (stage / "media" / "sentinel").write_bytes(b"synthetic abandoned copy")
    app_state.prepare_versioned_state(tmp_path, "2.0.0")
    assert not stage.exists()


def test_recovery_retains_replacement_after_stage_inspection(monkeypatch, tmp_path, caplog):
    app_state.prepare_versioned_state(tmp_path, "1.0.0")
    root = tmp_path / "state"
    stage = root / (".dds-stage-" + "c" * 32)
    stage.mkdir()
    (stage / ".stage-owner.json").write_text(
        json.dumps({"schema": 1, "stage": stage.name, "kind": "dds-state-initialization"})
    )
    guard = state_staging.directory_guard
    saved = tmp_path / "inspected"
    active_stage_guards = 0

    @contextmanager
    def replace_after_inspection(path, **kwargs):
        nonlocal active_stage_guards
        if path != stage:
            with guard(path, **kwargs) as descriptor:
                yield descriptor
            return
        active_stage_guards += 1
        try:
            with guard(path, **kwargs) as descriptor:
                yield descriptor
        finally:
            active_stage_guards -= 1
        if active_stage_guards == 0:
            stage.rename(saved)
            stage.mkdir()
            (stage / "unrelated").write_bytes(b"synthetic replacement")

    monkeypatch.setattr(state_staging, "directory_guard", replace_after_inspection)

    app_state.prepare_versioned_state(tmp_path, "2.0.0")

    assert (stage / "unrelated").read_bytes() == b"synthetic replacement"
    assert (saved / ".stage-owner.json").is_file()
    assert "Retained ambiguous abandoned state stage" in caplog.text


def test_recovery_removes_empty_retirement_when_stage_changes_before_detach(
    monkeypatch, tmp_path, caplog
):
    app_state.prepare_versioned_state(tmp_path, "1.0.0")
    root = tmp_path / "state"
    stage = root / (".dds-stage-" + "d" * 32)
    stage.mkdir()
    (stage / ".stage-owner.json").write_text(
        json.dumps({"schema": 1, "stage": stage.name, "kind": "dds-state-initialization"})
    )
    guard = state_staging.directory_guard
    saved = tmp_path / "inspected"

    @contextmanager
    def replace_after_retirement_created(path, **kwargs):
        if path.name.startswith(".dds-retired-") and stage.exists() and not saved.exists():
            stage.rename(saved)
            stage.mkdir()
            (stage / "unrelated").write_bytes(b"synthetic replacement")
        with guard(path, **kwargs) as descriptor:
            yield descriptor

    monkeypatch.setattr(state_staging, "directory_guard", replace_after_retirement_created)

    app_state.prepare_versioned_state(tmp_path, "2.0.0")
    app_state.prepare_versioned_state(tmp_path, "2.0.0")

    assert (stage / "unrelated").read_bytes() == b"synthetic replacement"
    assert (saved / ".stage-owner.json").is_file()
    assert not [entry for entry in root.iterdir() if entry.name.startswith(".dds-retired-")]
    assert "Retained ambiguous abandoned state stage" in caplog.text
