import uuid

import pytest

from tests.conftest import register_and_verify


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def create_project(client, token, name="Test Project"):
    resp = client.post(
        "/api/v1/projects/",
        json={"name": name, "description": "For agent testing"},
        headers=auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def create_agent(client, token, project_id, **overrides):
    payload = {
        "name": "Test Agent",
        "description": "A test agent",
        "model": "gpt-4o",
        "system_prompt": "You are a helpful assistant.",
        "temperature": 0.7,
    }
    payload.update(overrides)
    return client.post(
        f"/api/v1/projects/{project_id}/agents",
        json=payload,
        headers=auth(token),
    )


@pytest.fixture
def setup(client):
    token, _ = register_and_verify(client, f"alice-{uuid.uuid4()}@example.com")
    project_id = create_project(client, token)
    return {"token": token, "project_id": project_id}


@pytest.fixture
def other_user(client):
    return register_and_verify(client, f"bob-{uuid.uuid4()}@example.com")[0]


class TestCreateAgent:
    def test_create_agent(self, client, setup):
        resp = create_agent(client, setup["token"], setup["project_id"])
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Test Agent"
        assert body["model"] == "gpt-4o"
        assert body["project_id"] == setup["project_id"]
        assert body["status"] == "inactive"
        assert body["is_public"] is False

    def test_requires_authentication(self, client, setup):
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}/agents",
            json={"name": "No auth"},
        )
        assert resp.status_code == 401

    def test_project_not_found(self, client, setup):
        resp = create_agent(client, setup["token"], 9999)
        assert resp.status_code == 404

    def test_cannot_create_in_another_users_project(self, client, setup, other_user):
        resp = create_agent(client, other_user, setup["project_id"])
        assert resp.status_code == 404

    def test_rejects_empty_name(self, client, setup):
        resp = create_agent(client, setup["token"], setup["project_id"], name="")
        assert resp.status_code == 422

    def test_rejects_invalid_status(self, client, setup):
        resp = create_agent(
            client,
            setup["token"],
            setup["project_id"],
            status="destroyed",
        )
        assert resp.status_code == 422


class TestListAgents:
    def test_list_agents(self, client, setup):
        create_agent(client, setup["token"], setup["project_id"], name="Agent A")
        create_agent(client, setup["token"], setup["project_id"], name="Agent B")
        resp = client.get(
            f"/api/v1/projects/{setup['project_id']}/agents",
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 200
        names = {a["name"] for a in resp.json()}
        assert names == {"Agent A", "Agent B"}

    def test_cannot_list_another_users_project(self, client, setup, other_user):
        resp = client.get(
            f"/api/v1/projects/{setup['project_id']}/agents",
            headers=auth(other_user),
        )
        assert resp.status_code == 404


class TestGetAgent:
    def test_get_agent(self, client, setup):
        created = create_agent(client, setup["token"], setup["project_id"]).json()
        resp = client.get(
            f"/api/v1/projects/{setup['project_id']}/agents/{created['id']}",
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_cannot_get_another_users_agent(self, client, setup, other_user):
        created = create_agent(client, setup["token"], setup["project_id"]).json()
        resp = client.get(
            f"/api/v1/projects/{setup['project_id']}/agents/{created['id']}",
            headers=auth(other_user),
        )
        assert resp.status_code == 404


class TestUpdateAgent:
    def test_update_agent(self, client, setup):
        created = create_agent(client, setup["token"], setup["project_id"]).json()
        resp = client.patch(
            f"/api/v1/projects/{setup['project_id']}/agents/{created['id']}",
            json={"name": "Renamed", "temperature": 1.0},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Renamed"
        assert body["temperature"] == 1.0

    def test_update_invalid_status(self, client, setup):
        created = create_agent(client, setup["token"], setup["project_id"]).json()
        resp = client.patch(
            f"/api/v1/projects/{setup['project_id']}/agents/{created['id']}",
            json={"status": "gone"},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 422

    def test_update_missing_agent(self, client, setup):
        resp = client.patch(
            f"/api/v1/projects/{setup['project_id']}/agents/9999",
            json={"name": "Nope"},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 404


class TestArchiveAgent:
    def test_archive_agent(self, client, setup):
        created = create_agent(client, setup["token"], setup["project_id"]).json()
        resp = client.delete(
            f"/api/v1/projects/{setup['project_id']}/agents/{created['id']}",
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 204

        # archived agents are no longer visible
        get_resp = client.get(
            f"/api/v1/projects/{setup['project_id']}/agents/{created['id']}",
            headers=auth(setup["token"]),
        )
        assert get_resp.status_code == 404

    def test_archive_missing_agent(self, client, setup):
        resp = client.delete(
            f"/api/v1/projects/{setup['project_id']}/agents/9999",
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 404


    def test_get_missing_agent(self, client, setup):
        resp = client.get(
            f"/api/v1/projects/{setup['project_id']}/agents/9999",
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 404
