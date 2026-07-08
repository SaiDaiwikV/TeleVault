"""Files & folders: upload/download round-trip, dedup, ownership, share links."""
import io


def _upload(client, content: bytes, name: str = "note.txt", folder_id=None):
    files = {"upload": (name, io.BytesIO(content), "text/plain")}
    data = {"encrypted": "false"}
    if folder_id is not None:
        data["folder_id"] = str(folder_id)
    return client.post("/api/files", files=files, data=data)


def test_upload_download_roundtrip(auth_client):
    payload = b"hello televault" * 200  # spans multiple 1KB fake chunks
    up = _upload(auth_client, payload)
    assert up.status_code == 200, up.text
    file_id = up.json()["id"]
    assert up.json()["size"] == len(payload)
    assert len(up.json()["chunks"]) >= 2  # actually chunked

    down = auth_client.get(f"/api/files/{file_id}/download")
    assert down.status_code == 200
    assert down.content == payload


def test_empty_file_roundtrip(auth_client):
    up = _upload(auth_client, b"", name="empty.txt")
    assert up.status_code == 200
    file_id = up.json()["id"]
    down = auth_client.get(f"/api/files/{file_id}/download")
    assert down.status_code == 200
    assert down.content == b""


def test_dedup_reuses_chunks(auth_client):
    content = b"identical bytes"
    first = _upload(auth_client, content, name="a.txt").json()
    second = _upload(auth_client, content, name="b.txt").json()
    assert second["deduplicated"] is True
    # Same underlying Telegram messages reused, not re-sent.
    assert [c["tg_message_id"] for c in first["chunks"]] == [
        c["tg_message_id"] for c in second["chunks"]
    ]


def test_delete_keeps_deduped_sibling_downloadable(auth_client):
    content = b"shared content"
    a = _upload(auth_client, content, name="a.txt").json()
    b = _upload(auth_client, content, name="b.txt").json()
    # Delete a; b shares the same messages and must still download intact.
    assert auth_client.delete(f"/api/files/{a['id']}").status_code == 200
    down = auth_client.get(f"/api/files/{b['id']}/download")
    assert down.status_code == 200
    assert down.content == content


def test_folder_crud_and_nesting(auth_client):
    root = auth_client.post("/api/folders", json={"name": "Docs"}).json()
    child = auth_client.post("/api/folders", json={"name": "2026", "parent_id": root["id"]}).json()
    assert child["parent_id"] == root["id"]

    # Non-empty folder can't be deleted.
    assert auth_client.delete(f"/api/folders/{root['id']}").status_code == 409

    # Delete child first, then root.
    assert auth_client.delete(f"/api/folders/{child['id']}").status_code == 200
    assert auth_client.delete(f"/api/folders/{root['id']}").status_code == 200


def test_move_folder_reparents(auth_client):
    a = auth_client.post("/api/folders", json={"name": "A"}).json()
    b = auth_client.post("/api/folders", json={"name": "B"}).json()
    moved = auth_client.patch(f"/api/folders/{b['id']}/move", json={"folder_id": a["id"]})
    assert moved.status_code == 200
    assert moved.json()["parent_id"] == a["id"]


def test_move_folder_into_own_descendant_rejected(auth_client):
    parent = auth_client.post("/api/folders", json={"name": "Parent"}).json()
    child = auth_client.post("/api/folders", json={"name": "Child", "parent_id": parent["id"]}).json()
    # Moving Parent under its own Child would create a cycle.
    resp = auth_client.patch(f"/api/folders/{parent['id']}/move", json={"folder_id": child["id"]})
    assert resp.status_code == 409


def test_move_folder_into_itself_rejected(auth_client):
    f = auth_client.post("/api/folders", json={"name": "Self"}).json()
    resp = auth_client.patch(f"/api/folders/{f['id']}/move", json={"folder_id": f["id"]})
    assert resp.status_code == 409


def test_move_folder_name_clash_rejected(auth_client):
    dest = auth_client.post("/api/folders", json={"name": "Dest"}).json()
    # An existing "Docs" inside Dest ...
    auth_client.post("/api/folders", json={"name": "Docs", "parent_id": dest["id"]})
    # ... blocks moving a root-level "Docs" into Dest.
    root_docs = auth_client.post("/api/folders", json={"name": "Docs"}).json()
    resp = auth_client.patch(f"/api/folders/{root_docs['id']}/move", json={"folder_id": dest["id"]})
    assert resp.status_code == 409


def test_rename_and_move_file(auth_client):
    folder = auth_client.post("/api/folders", json={"name": "Target"}).json()
    file = _upload(auth_client, b"data").json()

    renamed = auth_client.patch(f"/api/files/{file['id']}/rename", json={"name": "renamed.txt"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "renamed.txt"

    moved = auth_client.patch(f"/api/files/{file['id']}/move", json={"folder_id": folder["id"]})
    assert moved.status_code == 200
    listing = auth_client.get(f"/api/items?folder_id={folder['id']}").json()
    assert any(f["id"] == file["id"] for f in listing["files"])


def test_search_matches_name(auth_client):
    _upload(auth_client, b"x", name="quarterly-report.pdf")
    _upload(auth_client, b"y", name="cat-photo.png")
    hits = auth_client.get("/api/items?q=report").json()
    names = [f["name"] for f in hits["files"]]
    assert "quarterly-report.pdf" in names
    assert "cat-photo.png" not in names


def test_cannot_access_another_users_file(client):
    # alice uploads
    tok_a = client.post("/api/auth/register", json={"username": "alice", "password": "password123"}).json()["token"]
    client.headers.update({"Authorization": f"Bearer {tok_a}"})
    file_id = _upload(client, b"secret").json()["id"]

    # mallory tries to read it
    tok_m = client.post("/api/auth/register", json={"username": "mallory", "password": "password123"}).json()["token"]
    client.headers.update({"Authorization": f"Bearer {tok_m}"})
    assert client.get(f"/api/files/{file_id}/download").status_code == 404
    assert client.delete(f"/api/files/{file_id}").status_code == 404


def test_max_upload_size_enforced(auth_client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_bytes", 10)
    resp = _upload(auth_client, b"way more than ten bytes", name="big.bin")
    assert resp.status_code == 413


# ── share links ──────────────────────────────────────────────────────────────


def test_share_link_download_and_revoke(auth_client):
    content = b"shareable content"
    file_id = _upload(auth_client, content).json()["id"]

    share = auth_client.post(f"/api/files/{file_id}/share", json={}).json()
    token = share["token"]

    # Public download (no auth header needed) returns the ciphertext bytes.
    pub = auth_client.get(f"/api/share/{token}/download")
    assert pub.status_code == 200
    assert pub.content == content

    # Revoke → now gone.
    share_id = auth_client.get(f"/api/files/{file_id}/shares").json()[0]["id"]
    assert auth_client.delete(f"/api/shares/{share_id}").status_code == 200
    assert auth_client.get(f"/api/share/{token}/download").status_code == 404


def test_share_link_download_limit(auth_client):
    file_id = _upload(auth_client, b"limited").json()["id"]
    token = auth_client.post(f"/api/files/{file_id}/share", json={"max_downloads": 1}).json()["token"]

    assert auth_client.get(f"/api/share/{token}/download").status_code == 200
    # Second download exceeds the cap.
    assert auth_client.get(f"/api/share/{token}/download").status_code == 410


def test_content_disposition_filename_used(auth_client):
    file_id = _upload(auth_client, b"data", name="report final.txt").json()["id"]
    down = auth_client.get(f"/api/files/{file_id}/download")
    assert "report final.txt" in down.headers["content-disposition"]
