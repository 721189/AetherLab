import uuid

import pytest

from tests.conftest import register_and_verify


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_a(client):
    return register_and_verify(client, f"alice-{uuid.uuid4()}@example.com")[0]


@pytest.fixture
def user_b(client):
    return register_and_verify(client, f"bob-{uuid.uuid4()}@example.com")[0]


def create_project(client, token, **overrides):
    payload = {"name": "My Project", "description": "A test project"}
    payload.update(overrides)
    return client.post(
        "/api/v1/projects/",
        json=payload,
        headers=auth(token),
    )


class TestCreateProject:
    def test_requires_authentication(self, client):
        resp = client.post(
            "/api/v1/projects/",
            json={"name": "No token"},
        )
        assert resp.status_code == 401

    def test_create_project(self, client, user_a):
        resp = create_project(client, user_a)
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "My Project"
        assert body["description"] == "A test project"
        assert body["is_archived"] is False
        assert body["id"] == 1

    def test_rejects_empty_name(self, client, user_a):
        resp = create_project(client, user_a, name="")
        assert resp.status_code == 422


class TestListProjects:
    def test_list_projects(self, client, user_a):
        create_project(client, user_a, name="P1")
        create_project(client, user_a, name="P2")
        resp = client.get("/api/v1/projects/", headers=auth(user_a))
        assert resp.status_code == 200
        bodies = resp.json()
        assert len(bodies) == 2
        assert {p["name"] for p in bodies} == {"P1", "P2"}

    def test_users_only_see_own_projects(self, client, user_a, user_b):
        create_project(client, user_a, name="Alice Project")
        resp = client.get("/api/v1/projects/", headers=auth(user_b))
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetProject:
    def test_get_own_project(self, client, user_a):
        created = create_project(client, user_a).json()
        resp = client.get(
            f"/api/v1/projects/{created['id']}",
            headers=auth(user_a),
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_cannot_get_another_users_project(self, client, user_a, user_b):
        created = create_project(client, user_a).json()
        resp = client.get(
            f"/api/v1/projects/{created['id']}",
            headers=auth(user_b),
        )
        assert resp.status_code == 404

    def test_get_missing_project(self, client, user_a):
        resp = client.get("/api/v1/projects/999", headers=auth(user_a))
        assert resp.status_code == 404


class TestUpdateProject:
    def test_update_project(self, client, user_a):
        created = create_project(client, user_a).json()
        resp = client.patch(
            f"/api/v1/projects/{created['id']}",
            json={"name": "Renamed"},
            headers=auth(user_a),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"

    def test_update_missing_project(self, client, user_a):
        resp = client.patch(
            "/api/v1/projects/999",
            json={"name": "Nope"},
            headers=auth(user_a),
        )
        assert resp.status_code == 404


class TestDeleteProject:
    def test_delete_archives_project(self, client, user_a):
        created = create_project(client, user_a).json()
        resp = client.delete(
            f"/api/v1/projects/{created['id']}",
            headers=auth(user_a),
        )
        assert resp.status_code == 204

        # soft-deleted project no longer visible
        get_resp = client.get(
            f"/api/v1/projects/{created['id']}",
            headers=auth(user_a),
        )
        assert get_resp.status_code == 404

    def test_delete_missing_project(self, client, user_a):
        resp = client.delete("/api/v1/projects/999", headers=auth(user_a))
        assert resp.status_code == 404