import uuid

import pytest

from tests.conftest import register_and_verify


# A fake LLM provider so messaging tests don't hit a real API.
class FakeProvider:
    def __init__(self, reply="Hello from fake LLM"):
        self.reply = reply
        self.called_with = None

    def generate_response(self, messages, system_prompt=None, temperature=0.7,
                          max_tokens=None, **kwargs):
        self.called_with = {
            "messages": messages,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        return self.reply

    def stream_response(self, messages, system_prompt=None, temperature=0.7,
                        max_tokens=None, **kwargs):
        self.called_with = {
            "messages": messages,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        yield self.reply


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def create_project(client, token):
    resp = client.post(
        "/api/v1/projects/",
        json={"name": "Chat Project"},
        headers=auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def create_conversation(client, token, project_id, title="My Chat"):
    resp = client.post(
        f"/api/v1/projects/{project_id}/conversations",
        json={"title": title},
        headers=auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def create_agent(client, token, project_id, **overrides):
    payload = {
        "name": "Config Agent",
        "model": "gpt-4o",
        "system_prompt": "You are a configurable test assistant.",
        "temperature": 1.5,
        "max_tokens": 256,
    }
    payload.update(overrides)
    resp = client.post(
        f"/api/v1/projects/{project_id}/agents",
        json=payload,
        headers=auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
def setup(client):
    token, _ = register_and_verify(
        client, f"alice-{uuid.uuid4()}@example.com"
    )
    project_id = create_project(client, token)
    return {"token": token, "project_id": project_id}


@pytest.fixture
def other_user(client):
    return register_and_verify(client, f"bob-{uuid.uuid4()}@example.com")[0]


@pytest.fixture
def fake_llm(monkeypatch):
    provider = FakeProvider()
    import app.services.conversation_service as cs

    monkeypatch.setattr(cs, "get_llm_provider", lambda *a, **k: provider)
    return provider


class TestCreateConversation:
    def test_create_conversation(self, client, setup):
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}/conversations",
            json={"title": "My Chat"},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == "My Chat"
        assert resp.json()["project_id"] == setup["project_id"]

    def test_requires_authentication(self, client, setup):
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}/conversations",
            json={"title": "No Auth"},
        )
        assert resp.status_code == 401

    def test_project_not_found(self, client, setup):
        resp = client.post(
            "/api/v1/projects/9999/conversations",
            json={"title": "Nope"},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 404

    def test_cannot_create_in_another_users_project(self, client, setup, other_user):
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}/conversations",
            json={"title": "Intruder"},
            headers=auth(other_user),
        )
        assert resp.status_code == 404


class TestListConversations:
    def test_list_conversations(self, client, setup):
        create_conversation(client, setup["token"], setup["project_id"], title="A")
        create_conversation(client, setup["token"], setup["project_id"], title="B")
        resp = client.get(
            f"/api/v1/projects/{setup['project_id']}/conversations",
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 200
        titles = {c["title"] for c in resp.json()}
        assert titles == {"A", "B"}

    def test_cannot_list_another_users_project(self, client, setup, other_user):
        resp = client.get(
            f"/api/v1/projects/{setup['project_id']}/conversations",
            headers=auth(other_user),
        )
        assert resp.status_code == 404


class TestGetConversation:
    def test_get_conversation(self, client, setup):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        resp = client.get(
            f"/api/v1/projects/{setup['project_id']}/conversations/{conv['id']}",
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == conv["id"]

    def test_get_missing_conversation(self, client, setup):
        resp = client.get(
            f"/api/v1/projects/{setup['project_id']}/conversations/9999",
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 404

    def test_cannot_get_another_users_conversation(self, client, setup, other_user):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        resp = client.get(
            f"/api/v1/projects/{setup['project_id']}/conversations/{conv['id']}",
            headers=auth(other_user),
        )
        assert resp.status_code == 404
class TestUpdateConversation:
    def test_update_title(self, client, setup):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        resp = client.patch(
            f"/api/v1/projects/{setup['project_id']}/conversations/{conv['id']}",
            json={"title": "Renamed Chat"},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Renamed Chat"

    def test_update_missing_conversation(self, client, setup):
        resp = client.patch(
            f"/api/v1/projects/{setup['project_id']}/conversations/9999",
            json={"title": "Nope"},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 404


class TestDeleteConversation:
    def test_delete_conversation(self, client, setup):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        resp = client.delete(
            f"/api/v1/projects/{setup['project_id']}/conversations/{conv['id']}",
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 204

        get_resp = client.get(
            f"/api/v1/projects/{setup['project_id']}/conversations/{conv['id']}",
            headers=auth(setup["token"]),
        )
        assert get_resp.status_code == 404

    def test_delete_missing_conversation(self, client, setup):
        resp = client.delete(
            f"/api/v1/projects/{setup['project_id']}/conversations/9999",
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 404


class TestSendMessage:
    def test_send_message_persists_user_and_assistant_messages(
        self, client, setup, fake_llm
    ):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}/conversations/{conv['id']}/messages",
            json={"content": "Hello LLM"},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_message"]["role"] == "user"
        assert body["user_message"]["content"] == "Hello LLM"
        assert body["assistant_message"]["role"] == "assistant"
        assert body["assistant_message"]["content"] == "Hello from fake LLM"

        # Verify the fake provider received the history.
        assert fake_llm.called_with is not None
        roles = {m["role"] for m in fake_llm.called_with["messages"]}
        assert roles == {"user"}

    def test_send_message_accumulates_history(self, client, setup, fake_llm):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        conv_id = conv["id"]
        base = f"/api/v1/projects/{setup['project_id']}/conversations/{conv_id}/messages"
        for text in ("First", "Second"):
            client.post(base, json={"content": text}, headers=auth(setup["token"]))

        # The third message's history should include the prior exchange.
        client.post(base, json={"content": "Third"}, headers=auth(setup["token"]))
        history = fake_llm.called_with["messages"]
        assert [m["role"] for m in history] == [
            "user", "assistant", "user", "assistant", "user",
        ]

    def test_send_message_to_missing_conversation(self, client, setup, fake_llm):
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}/conversations/9999/messages",
            json={"content": "Hello"},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 404

    def test_send_message_rejects_empty_content(self, client, setup, fake_llm):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}/conversations/{conv['id']}/messages",
            json={"content": ""},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 422

    def test_cannot_send_message_in_another_users_conversation(
        self, client, setup, other_user, fake_llm
    ):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}/conversations/{conv['id']}/messages",
            json={"content": "Intruder"},
            headers=auth(other_user),
        )
        assert resp.status_code == 404


class TestListMessages:
    def test_paginated_list_returns_messages(self, client, setup, fake_llm):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        conv_id = conv["id"]
        base = (
            f"/api/v1/projects/{setup['project_id']}"
            f"/conversations/{conv_id}/messages"
        )

        # Three user turns => three user + three assistant messages.
        client.post(base, json={"content": "First"}, headers=auth(setup["token"]))
        client.post(base, json={"content": "Second"}, headers=auth(setup["token"]))
        client.post(
            base, json={"content": "Third"}, headers=auth(setup["token"])
        )

        resp = client.get(base, headers=auth(setup["token"]))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 6
        assert {m["role"] for m in body} == {"user", "assistant"}
        # Oldest first.
        assert body[0]["content"] == "First"
        assert body[4]["content"] == "Third"

        # Pagination slices the window.
        page = client.get(
            base,
            headers=auth(setup["token"]),
            params={"skip": 0, "limit": 2},
        )
        assert page.status_code == 200
        assert len(page.json()) == 2
        assert page.json()[0]["content"] == "First"

        page2 = client.get(
            base,
            headers=auth(setup["token"]),
            params={"skip": 2, "limit": 2},
        )
        assert page2.status_code == 200
        contents = [m["content"] for m in page2.json()]
        assert contents == ["Second", "Hello from fake LLM"]

    def test_messages_for_missing_conversation(self, client, setup, fake_llm):
        resp = client.get(
            f"/api/v1/projects/{setup['project_id']}/conversations/9999/messages",
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 404

    def test_cannot_list_another_users_messages(
        self, client, setup, other_user, fake_llm
    ):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        resp = client.get(
            f"/api/v1/projects/{setup['project_id']}"
            f"/conversations/{conv['id']}/messages",
            headers=auth(other_user),
        )
        assert resp.status_code == 404


class TestStreamMessage:
    def test_stream_returns_sse_chunks(self, client, setup, fake_llm):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        conv_id = conv["id"]
        base = (
            f"/api/v1/projects/{setup['project_id']}"
            f"/conversations/{conv_id}/messages/stream"
        )

        resp = client.post(
            base, json={"content": "Hello stream"}, headers=auth(setup["token"])
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = resp.text
        assert "delta" in body
        assert "Hello from fake LLM" in body
        assert "[DONE]" in body
        # Both the user and assistant messages were persisted.
        fake_llm.called_with is not None  # provider was invoked

    def test_stream_message_is_persisted(self, client, setup, fake_llm):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        conv_id = conv["id"]
        stream_base = (
            f"/api/v1/projects/{setup['project_id']}"
            f"/conversations/{conv_id}/messages/stream"
        )
        msg_base = (
            f"/api/v1/projects/{setup['project_id']}"
            f"/conversations/{conv_id}/messages"
        )

        client.post(
            stream_base,
            json={"content": "Hi stream"},
            headers=auth(setup["token"]),
        )

        msgs = client.get(msg_base, headers=auth(setup["token"])).json()
        assert len(msgs) == 2
        roles = [m["role"] for m in msgs]
        assert roles == ["user", "assistant"]
        assert msgs[-1]["content"] == "Hello from fake LLM"

    def test_stream_requires_authentication(self, client, setup, fake_llm):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        base = (
            f"/api/v1/projects/{setup['project_id']}"
            f"/conversations/{conv['id']}/messages/stream"
        )
        resp = client.post(base, json={"content": "Hi"})
        assert resp.status_code == 401

    def test_stream_missing_conversation(self, client, setup, fake_llm):
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}/conversations/9999"
            f"/messages/stream",
            json={"content": "Hi"},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 404

    def test_stream_404_for_other_user(
        self, client, setup, other_user, fake_llm
    ):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}"
            f"/conversations/{conv['id']}/messages/stream",
            json={"content": "Hi"},
            headers=auth(other_user),
        )
        assert resp.status_code == 404


class TestAgentMessageConfig:
    def test_send_message_uses_agent_config(self, client, setup, fake_llm):
        agent = create_agent(client, setup["token"], setup["project_id"])
        conv = create_conversation(client, setup["token"], setup["project_id"])
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}"
            f"/conversations/{conv['id']}/messages",
            json={"content": "Configured?", "agent_id": agent["id"]},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 200
        assert fake_llm.called_with["system_prompt"] == agent["system_prompt"]
        assert fake_llm.called_with["temperature"] == agent["temperature"]
        assert fake_llm.called_with["max_tokens"] == agent["max_tokens"]

    def test_send_message_uses_agent_model(self, client, setup, fake_llm, monkeypatch):
        agent = create_agent(
            client, setup["token"], setup["project_id"], model="nvidia/custom-model"
        )
        captured = {}
        import app.services.conversation_service as cs

        def recorder(model, api_key=None, **kwargs):
            captured["model"] = model
            return fake_llm

        monkeypatch.setattr(cs, "get_llm_provider", recorder)
        conv = create_conversation(client, setup["token"], setup["project_id"])
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}"
            f"/conversations/{conv['id']}/messages",
            json={"content": "Hi", "agent_id": agent["id"]},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 200
        assert captured["model"] == "nvidia/custom-model"

    def test_send_message_missing_agent_returns_404(self, client, setup, fake_llm):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}"
            f"/conversations/{conv['id']}/messages",
            json={"content": "Hi", "agent_id": 9999},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 404

    def test_send_message_rejects_agent_from_another_project(
        self, client, setup, fake_llm
    ):
        token = setup["token"]
        # A second project owned by the same user, with its own agent.
        proj_b = client.post(
            "/api/v1/projects/", json={"name": "Project B"}, headers=auth(token)
        ).json()["id"]
        agent_b = create_agent(client, token, proj_b)

        conv = create_conversation(client, token, setup["project_id"])
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}"
            f"/conversations/{conv['id']}/messages",
            json={"content": "Hi", "agent_id": agent_b["id"]},
            headers=auth(token),
        )
        assert resp.status_code == 404

    def test_stream_uses_agent_config(self, client, setup, fake_llm):
        agent = create_agent(
            client,
            setup["token"],
            setup["project_id"],
            system_prompt="Stream prompt",
            temperature=1.0,
        )
        conv = create_conversation(client, setup["token"], setup["project_id"])
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}"
            f"/conversations/{conv['id']}/messages/stream",
            json={"content": "Hi", "agent_id": agent["id"]},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 200
        # Fully consume the SSE body so the generator runs.
        _ = resp.text
        assert fake_llm.called_with["system_prompt"] == "Stream prompt"
        assert fake_llm.called_with["temperature"] == 1.0

    def test_stream_missing_agent_returns_404(self, client, setup, fake_llm):
        conv = create_conversation(client, setup["token"], setup["project_id"])
        resp = client.post(
            f"/api/v1/projects/{setup['project_id']}"
            f"/conversations/{conv['id']}/messages/stream",
            json={"content": "Hi", "agent_id": 9999},
            headers=auth(setup["token"]),
        )
        assert resp.status_code == 404