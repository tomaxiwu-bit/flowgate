from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services.sample_cache import _resolve_fcs_path, _storage_path, drop_sample


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    settings = get_settings()
    uploads = tmp_path / "uploads"
    gates = tmp_path / "gates"
    uploads.mkdir()
    gates.mkdir()
    monkeypatch.setattr(settings, "upload_dir", uploads)
    monkeypatch.setattr(settings, "gates_dir", gates)
    file_id = uuid4().hex
    sample_dir = uploads / file_id
    sample_dir.mkdir()
    (sample_dir / "fixture.FCS").write_bytes(b"path checks only")
    yield TestClient(app, raise_server_exceptions=False), file_id, tmp_path


@pytest.mark.parametrize("file_id", ["..\\escaped", "../escaped", "C:\\escaped", "not-an-id", "a" * 33])
def test_storage_paths_reject_untrusted_ids(tmp_path, file_id):
    with pytest.raises(FileNotFoundError):
        _storage_path(tmp_path, file_id, ".json")
    with pytest.raises(FileNotFoundError):
        drop_sample(file_id)


def test_encoded_windows_traversal_cannot_write_or_read_outside_store(isolated_store):
    client, _, root = isolated_store
    marker = root / "escaped.json"
    marker.write_text('{"gates":[]}', encoding="utf-8")
    before = marker.read_bytes()
    url = "/api/files/%2e%2e%5cescaped/gates"
    assert client.get(url).status_code == 404
    assert client.put(url, json={"gates": []}).status_code == 404
    assert marker.read_bytes() == before
    assert not list((root / "gates").iterdir())


def test_unknown_upload_cannot_create_or_import_gates(isolated_store):
    client, _, root = isolated_store
    unknown = uuid4().hex
    assert client.put(f"/api/files/{unknown}/gates", json={"gates": []}).status_code == 404
    assert client.post(f"/api/files/{unknown}/gatingml/import", files={"file": ("test.xml", b"<xml/>")}).status_code == 404
    assert not (root / "gates" / f"{unknown}.json").exists()


def test_uppercase_extension_and_valid_gate_storage_still_work(isolated_store):
    client, file_id, root = isolated_store
    assert Path(_resolve_fcs_path(file_id)).name == "fixture.FCS"
    assert client.put(f"/api/files/{file_id}/gates", json={"gates": []}).status_code == 200
    assert client.get(f"/api/files/{file_id}/gates").json() == {"gates": []}
    assert [p.name for p in (root / "gates").iterdir()] == [f"{file_id}.json"]


def gate(gate_id, parent=None):
    return {"id": gate_id, "name": gate_id, "type": "rect", "x_label": "FSC-A", "y_label": "SSC-A",
            "x_min": 0, "x_max": 10, "y_min": 0, "y_max": 10, "parent_id": parent}


@pytest.mark.parametrize("gates", [
    [gate("root"), gate("a", "b"), gate("b", "a")],
    [gate("root"), gate("root")],
    [dict(gate("polygon"), type="polygon", vertices=[[1], [2], [3]])],
    [dict(gate("reversed"), x_min=20, x_max=10)],
])
def test_invalid_gate_payloads_rejected_before_save_and_evaluation(isolated_store, gates):
    client, file_id, root = isolated_store
    for endpoint, method in [("gates", client.put), ("gates/evaluate", client.post)]:
        assert method(f"/api/files/{file_id}/{endpoint}", json={"gates": gates}).status_code == 422
    assert not (root / "gates" / f"{file_id}.json").exists()


def test_storage_rejects_symlinks_outside_the_root(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    file_id = uuid4().hex
    try:
        (store / file_id).symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("This Windows account cannot create symlinks")
    with pytest.raises(FileNotFoundError):
        _storage_path(store, file_id)


def test_untrusted_hosts_cannot_reach_local_files(isolated_store):
    client, file_id, _ = isolated_store
    assert client.get(f"/api/files/{file_id}/gates", headers={"host": "untrusted.example"}).status_code == 400


def test_foreign_browser_writes_do_not_modify_gates(isolated_store):
    client, file_id, root = isolated_store
    response = client.put(f"/api/files/{file_id}/gates", json={"gates": []}, headers={"origin": "https://untrusted.example"})
    assert response.status_code == 403
    assert not (root / "gates" / f"{file_id}.json").exists()


def test_configured_frontend_origin_can_save_gates(isolated_store):
    client, file_id, _ = isolated_store
    response = client.put(f"/api/files/{file_id}/gates", json={"gates": []}, headers={"origin": "http://localhost:3000"})
    assert response.status_code == 200
