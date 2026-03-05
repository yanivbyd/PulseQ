import json
import pytest
import openai
from unittest.mock import MagicMock, patch

from scout.scout import build_prompt, parse_response, run


INSTRUCTIONS = "You are a scout. Find great tech topics."
USER_TASTES = "Aimed at senior engineers. Prefer deep dives into backend and infra."
TOPICS = [
    {"title": "How Kafka Works", "description": "Deep dive into Kafka internals."},
    {"title": "Load Balancers 101", "description": "How load balancers distribute traffic."},
]
FEEDBACK_EVENTS = [
    {"articleId": "abc12", "articleTitle": "How Kafka Works", "reaction": "like"},
    {"articleId": "def34", "articleTitle": "PostgreSQL Internals", "reaction": "dislike"},
]
NEW_TOPICS = [{"title": f"Topic {i}", "description": f"Desc {i}."} for i in range(10)]


def mock_openai_client(topics):
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps(topics)))]
    )
    return client


# ── build_prompt ──────────────────────────────────────────────────────────────

def test_build_prompt():
    system, user = build_prompt(INSTRUCTIONS, USER_TASTES, TOPICS, FEEDBACK_EVENTS)
    assert INSTRUCTIONS in system
    assert USER_TASTES in system                # user tastes in system prompt
    assert "How Kafka Works" in user            # topics in user prompt
    assert "PostgreSQL Internals" in user       # feedback events in user prompt
    assert '"reaction": "dislike"' in user      # full event JSON


def test_build_prompt_no_feedback():
    _, user = build_prompt(INSTRUCTIONS, USER_TASTES, TOPICS, [])
    assert "(none)" in user


# ── parse_response ────────────────────────────────────────────────────────────

def test_parse_response_plain_json():
    assert parse_response(json.dumps(NEW_TOPICS)) == NEW_TOPICS


def test_parse_response_json_fence():
    assert parse_response(f"```json\n{json.dumps(NEW_TOPICS)}\n```") == NEW_TOPICS


def test_parse_response_plain_fence():
    assert parse_response(f"```\n{json.dumps(NEW_TOPICS)}\n```") == NEW_TOPICS


def test_parse_response_invalid_raises():
    with pytest.raises(json.JSONDecodeError):
        parse_response("not json")


def test_parse_response_non_list_raises():
    with pytest.raises(ValueError, match="JSON array"):
        parse_response('{"title": "oops"}')


def test_parse_response_missing_fields_raises():
    with pytest.raises(ValueError, match="title.*description"):
        parse_response('[{"title": "no description"}]')


# ── run ───────────────────────────────────────────────────────────────────────

def test_run_happy_path_and_logs():
    client = mock_openai_client(NEW_TOPICS)
    with patch("scout.scout.openai.OpenAI", return_value=client), \
         patch("scout.scout.logger.info") as info_spy:
        result = run(INSTRUCTIONS, USER_TASTES, TOPICS, FEEDBACK_EVENTS, api_key="test-key")
    assert result == NEW_TOPICS
    info_spy.assert_called_once()
    assert info_spy.call_args[0][1] == 10  # count argument


def test_run_prompt_content():
    client = mock_openai_client(NEW_TOPICS)
    with patch("scout.scout.openai.OpenAI", return_value=client):
        run(INSTRUCTIONS, USER_TASTES, TOPICS, FEEDBACK_EVENTS, api_key="test-key")
    messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert INSTRUCTIONS in messages[0]["content"]
    assert USER_TASTES in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "PostgreSQL Internals" in messages[1]["content"]


def test_run_no_feedback_events():
    client = mock_openai_client(NEW_TOPICS)
    with patch("scout.scout.openai.OpenAI", return_value=client):
        result = run(INSTRUCTIONS, USER_TASTES, TOPICS, [], api_key="test-key")
    assert result == NEW_TOPICS
    user_prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "(none)" in user_prompt


def test_run_missing_api_key_raises():
    with pytest.raises(EnvironmentError):
        run(INSTRUCTIONS, USER_TASTES, TOPICS, FEEDBACK_EVENTS, api_key="")


def test_run_openai_error_propagates():
    client = MagicMock()
    client.chat.completions.create.side_effect = openai.OpenAIError("fail")
    with patch("scout.scout.openai.OpenAI", return_value=client):
        with pytest.raises(openai.OpenAIError):
            run(INSTRUCTIONS, USER_TASTES, TOPICS, FEEDBACK_EVENTS, api_key="test-key")


def test_run_invalid_json_response_raises():
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="not json at all"))]
    )
    with patch("scout.scout.openai.OpenAI", return_value=client), \
         patch("scout.scout.logger.error") as error_spy:
        with pytest.raises(json.JSONDecodeError):
            run(INSTRUCTIONS, USER_TASTES, TOPICS, FEEDBACK_EVENTS, api_key="test-key")
    error_spy.assert_called_once()
    assert "not json at all" in error_spy.call_args[0][1]


def test_run_invalid_structure_response_raises():
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='[{"title": "missing description"}]'))]
    )
    with patch("scout.scout.openai.OpenAI", return_value=client), \
         patch("scout.scout.logger.error") as error_spy:
        with pytest.raises(ValueError):
            run(INSTRUCTIONS, USER_TASTES, TOPICS, FEEDBACK_EVENTS, api_key="test-key")
    error_spy.assert_called_once()
