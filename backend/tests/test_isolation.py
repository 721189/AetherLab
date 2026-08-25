"""Cross-user authorization isolation tests (production security pass).

Verifies the core tenancy invariant everywhere it matters:

    User A must NEVER be able to read, modify or delete User B's resources.

Cross-owner access returns 404 (not 403) so resource existence is not leaked.
"""

import pytest

from tests.conftest import register_and_verify


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def two_users(client):
    """Register + verify + login two independent users; return their tokens."""
    token_a, payload_a = register_and_verify(client, "owner-a@example.com")
    token_b, payload_b = register_and_verify(client, "owner-b@example.com")
    return {
        "a": token_a,
        "b": token_b,
        "email_a": payload_a["email"],
        "email_b": payload_b["email"],
    }


def create_project(client, token, name="Secret plan"):
    resp = client.post("/api/v1/projects/", json={"name": name}, headers=auth(token))
    assert resp.status_code == 201
    return resp.json()


class TestProjectIsolation:
    def test_a_cannot_read_bs_project(self, client, two_users):
        project = create_project(client, two_users["a"])
        resp = client.get(f"/api/v1/projects/{project['id']}", headers=auth(two_users["b"]))
        assert resp.status_code == 404

    def test_a_cannot_update_bs_project(self, client, two_users):
        project = create_project(client, two_users["a"])
        resp = client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"name": "hijacked"},
            headers=auth(two_users["b"]),
        )
        assert resp.status_code == 404
        still = client.get(f"/api/v1/projects/{project['id']}", headers=auth(two_users["a"]))
        assert still.json()["name"] != "hijacked"

    def test_a_cannot_delete_bs_project(self, client, two_users):
        project = create_project(client, two_users["a"])
        resp = client.delete(f"/api/v1/projects/{project['id']}", headers=auth(two_users["b"]))
        assert resp.status_code == 404
        ok = client.get(f"/api/v1/projects/{project['id']}", headers=auth(two_users["a"]))
        assert ok.status_code == 200

    def test_listing_does_not_leak_other_users_projects(self, client, two_users):
        project = create_project(client, two_users["a"])
        listing = client.get("/api/v1/projects/", headers=auth(two_users["b"]))
        body = listing.json()
        rows = body if isinstance(body, list) else body.get("data", [])
        ids = [p["id"] for p in rows if isinstance(p, dict)]
        assert project["id"] not in ids


class TestAgentAndConversationIsolation:
    def test_a_cannot_read_bs_agents(self, client, two_users):
        project = create_project(client, two_users["a"])
        client.post(
            f"/api/v1/projects/{project['id']}/agents",
            json={"name": "secret-agent"},
            headers=auth(two_users["a"]),
        )
        resp = client.get(
            f"/api/v1/projects/{project['id']}/agents", headers=auth(two_users["b"])
        )
        assert resp.status_code == 404

    def test_b_cannot_create_agent_in_as_project(self, client, two_users):
        project = create_project(client, two_users["a"])
        resp = client.post(
            f"/api/v1/projects/{project['id']}/agents",
            json={"name": "intruder"},
            headers=auth(two_users["b"]),
        )
        assert resp.status_code == 404

    def test_b_cannot_read_bs_conversations(self, client, two_users):
        project = create_project(client, two_users["a"])
        created = client.post(
            f"/api/v1/projects/{project['id']}/conversations",
            json={"title": "private chat"},
            headers=auth(two_users["a"]),
        )
        conv_id = created.json()["id"]
        resp = client.get(
            f"/api/v1/projects/{project['id']}/conversations/{conv_id}",
            headers=auth(two_users["b"]),
        )
        assert resp.status_code == 404

    def test_b_cannot_post_to_bs_conversation(self, client, two_users):
        project = create_project(client, two_users["a"])
        created = client.post(
            f"/api/v1/projects/{project['id']}/conversations",
            json={"title": "private chat"},
            headers=auth(two_users["a"]),
        )
        conv_id = created.json()["id"]
        resp = client.post(
            f"/api/v1/projects/{project['id']}/conversations/{conv_id}/messages",
            json={"content": "malicious"},
            headers=auth(two_users["b"]),
        )
        assert resp.status_code == 404