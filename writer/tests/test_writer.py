import os
import pytest
import openai
from unittest.mock import patch, MagicMock

from writer.writer import generate_short_id, generate_quiz, generate_article, strip_markdown_fences


# ── Constants ────────────────────────────────────────────────────────────────

HTML_FRAGMENT = (
    "<style>:root { --accent: #0d9488; }</style>\n"
    "<div class=\"header-card\"><h1>Test Article</h1></div>"
)

QUIZ_JSON = '[{"q": "What protocol?", "options": ["QUIC", "TCP", "WebRTC"], "answer": 0}]'
QUIZ_PARSED = [{"q": "What protocol?", "options": ["QUIC", "TCP", "WebRTC"], "answer": 0}]


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_openai():
    """Return a mock OpenAI client whose first call returns HTML."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=HTML_FRAGMENT))]
    )
    return mock_client


# ── strip_markdown_fences ───────────────────────────────────────────────────

def test_strip_fences_no_fence():
    assert strip_markdown_fences("<p>hello</p>") == "<p>hello</p>"

def test_strip_fences_html_lang():
    assert strip_markdown_fences("```html\n<p>hi</p>\n```") == "<p>hi</p>"

def test_strip_fences_no_newline_after_lang():
    assert strip_markdown_fences("```html<p>hi</p>\n```") == "<p>hi</p>"

def test_strip_fences_no_newlines():
    assert strip_markdown_fences("```html<p>hi</p>```") == "<p>hi</p>"

def test_strip_fences_no_lang():
    assert strip_markdown_fences("```\n<p>hi</p>\n```") == "```\n<p>hi</p>\n```"

def test_strip_fences_trailing_whitespace():
    assert strip_markdown_fences("```html\n<p>hi</p>\n```  ") == "<p>hi</p>"

def test_strip_fences_inner_blank_lines():
    assert strip_markdown_fences("```html\n\n<p>hi</p>\n\n```") == "<p>hi</p>"

def test_strip_fences_logs_info(caplog):
    import logging
    with caplog.at_level(logging.INFO, logger="writer.writer"):
        strip_markdown_fences("```html\n<p>hi</p>\n```")
    assert caplog.records[-1].levelno == logging.INFO
    assert caplog.records[-1].message == "stripped markdown fence: ```html{content}```"  # fixed string, no interpolation


# ── generate_quiz ────────────────────────────────────────────────────────────

def test_shuffle_options_preserves_correct_answer():
    """After shuffling, the answer index still points to the original correct option."""
    from writer.writer import _shuffle_options
    quiz = [{"q": "Q?", "options": ["A", "B", "C"], "answer": 0}]
    with patch("writer.writer.random.shuffle", lambda lst: lst.reverse()):
        result = _shuffle_options(quiz)
    # reversed: ["C", "B", "A"], correct was "A" → now at index 2
    assert result[0]["options"] == ["C", "B", "A"]
    assert result[0]["answer"] == 2
    assert result[0]["options"][result[0]["answer"]] == "A"


def test_generate_quiz_happy_path():
    """Valid 1- and 2-question quiz JSON is parsed and returned as a list."""
    two_q = '[{"q": "Q1?", "options": ["A", "B", "C"], "answer": 1}, {"q": "Q2?", "options": ["X", "Y", "Z"], "answer": 2}]'

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=MagicMock(content=QUIZ_JSON))]),
        MagicMock(choices=[MagicMock(message=MagicMock(content=two_q))]),
    ]

    result_one = generate_quiz(mock_client, "<p>html</p>", "prompt")
    assert len(result_one) == 1
    # correct option text preserved after shuffle
    assert result_one[0]["options"][result_one[0]["answer"]] == QUIZ_PARSED[0]["options"][QUIZ_PARSED[0]["answer"]]

    result_two = generate_quiz(mock_client, "<p>html</p>", "prompt")
    assert len(result_two) == 2
    assert result_two[0]["options"][result_two[0]["answer"]] == "B"
    assert result_two[1]["options"][result_two[1]["answer"]] == "Z"


def test_generate_quiz_validation_failures_fall_back_to_empty(caplog):
    """Bad JSON, wrong count, and missing/invalid fields all fall back to [] with a warning."""
    import logging

    bad_cases = [
        "not json",                                                                    # bad JSON
        "[]",                                                                          # 0 items
        QUIZ_JSON.replace("]", "] extra"),                                             # JSON parse error
        '[{"q":"Q?","options":["A","B","C"],"answer":0},'                              # 3 items
        '{"q":"Q?","options":["A","B","C"],"answer":1},'
        '{"q":"Q?","options":["A","B","C"],"answer":2}]',
        '[{"options":["A","B","C"],"answer":0}]',                                      # missing q
        '[{"q":"Q?","options":["A","B","C"]}]',                                        # missing answer
        '[{"q":"Q?","options":["A","B","C"],"answer":3}]',                             # answer out of range
    ]

    for bad_content in bad_cases:
        caplog.clear()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=bad_content))]
        )
        with caplog.at_level(logging.WARNING, logger="writer.writer"):
            result = generate_quiz(mock_client, "<p>html</p>", "prompt")
        assert result == [], f"expected [] for: {bad_content!r}"
        assert any(r.levelno == logging.WARNING for r in caplog.records), f"expected warning for: {bad_content!r}"


# ── generate_article() ───────────────────────────────────────────────────────

def test_happy_path(mock_openai):
    """generate_article() returns a dict with id, html, title, and accent (no quiz)."""
    with patch("writer.writer.openai.OpenAI", return_value=mock_openai), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = generate_article(topic="N+1 Queries — Detection patterns.",
                                  article_instructions="Style instructions.")

    assert result["html"] == HTML_FRAGMENT
    assert result["title"] == "Test Article"
    assert result["accent"] == "#0d9488"
    assert len(result["id"]) == 5
    assert result["id"].isalnum()
    assert "quiz" not in result


def test_topic_included_in_prompt(mock_openai):
    """Topic string is passed verbatim to the OpenAI article prompt; no history section."""
    with patch("writer.writer.openai.OpenAI", return_value=mock_openai), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        generate_article(topic="My Topic", article_instructions="Instructions")

    call_args = mock_openai.chat.completions.create.call_args_list[0]
    user_message = call_args.kwargs["messages"][1]["content"]
    assert "My Topic" in user_message
    assert "HISTORY" not in user_message


def test_missing_api_key():
    """Missing OPENAI_API_KEY raises EnvironmentError before any API call."""
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(EnvironmentError):
            generate_article(topic="T", article_instructions="I")


def test_short_id_format():
    """generate_short_id returns a 5-character alphanumeric string."""
    id_ = generate_short_id()
    assert len(id_) == 5
    assert id_.isalnum()


def test_short_id_uniqueness():
    """Consecutive calls to generate_short_id return different values."""
    ids = {generate_short_id() for _ in range(20)}
    assert len(ids) > 1


def test_openai_error_propagates():
    """An OpenAI API error on article generation propagates as OpenAIError."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = openai.OpenAIError("api failure")
    with patch("writer.writer.openai.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with pytest.raises(openai.OpenAIError):
            generate_article(topic="T", article_instructions="I")


def test_accent_fallback():
    """When HTML has no --accent, accent defaults to #5b5ef4."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="<h1>No style</h1>"))]
    )
    with patch("writer.writer.openai.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = generate_article(topic="T", article_instructions="I")

    assert result["accent"] == "#5b5ef4"


def test_title_fallback():
    """When HTML has no h1, title defaults to 'New Article'."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="<p>No heading</p>"))]
    )
    with patch("writer.writer.openai.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = generate_article(topic="T", article_instructions="I")

    assert result["title"] == "New Article"
