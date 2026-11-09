import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

import fake_api  # noqa: E402
import weather_api  # noqa: E402
from app import create_app  # noqa: E402

TOKEN = "test-token"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(weather_api.requests, "get", fake_api.fake_get)


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "SECRET_KEY": "test",
                       "DATABASE": str(tmp_path / "test.db")})


def new_client(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["csrf"] = TOKEN
    return client


def token(client):
    with client.session_transaction() as sess:
        return sess.setdefault("csrf", TOKEN)


def register(client, username="alice"):
    return client.post("/register", data={"username": username, "password": "password123",
                                          "csrf_token": token(client)})


@pytest.fixture
def client(app):
    return new_client(app)


@pytest.fixture
def logged_in(client):
    register(client)
    return client
