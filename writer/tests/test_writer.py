import os
import pytest
import openai
from pathlib import Path
from unittest.mock import patch, MagicMock

from writer.writer import generate_short_id, run, strip_markdown_fences


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def input_files(tmp_path):
    """Create required input files."""
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "instructions.md").write_text("Style instructions.")
    return tmp_path


@pytest.fixture
def mock_openai():
    """Return a mock OpenAI client whose chat completion returns HTML."""
    fragment = (
        "<style>:root { --accent: #0d9488; }</style>\n"
        "<div class=\"header-card\"><h1>Test Article</h1></div>"
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=fragment))]
    )
    return mock_client, fragment


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


# ── Tests ───────────────────────────────────────────────────────────────────

def test_happy_path(input_files, mock_openai):
    """run() returns a dict with id, html, title, and accent."""
    mock_client, fragment = mock_openai
    with patch("writer.writer.openai.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run(base_dir=input_files, topic="N+1 Queries — Detection patterns.")

    assert result["html"] == fragment
    assert result["title"] == "Test Article"
    assert result["accent"] == "#0d9488"
    assert len(result["id"]) == 5
    assert result["id"].isalnum()


def test_topic_included_in_prompt(input_files, mock_openai):
    """Topic string is passed verbatim to the OpenAI prompt; no history section."""
    mock_client, _ = mock_openai
    with patch("writer.writer.openai.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        run(base_dir=input_files, topic="My Topic")

    call_args = mock_client.chat.completions.create.call_args
    user_message = call_args.kwargs["messages"][1]["content"]
    assert "My Topic" in user_message
    assert "HISTORY" not in user_message


def test_missing_instructions(input_files, mock_openai):
    """Missing instructions.md raises FileNotFoundError."""
    mock_client, _ = mock_openai
    (input_files / "inputs" / "instructions.md").unlink()
    with patch("writer.writer.openai.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with pytest.raises(FileNotFoundError):
            run(base_dir=input_files, topic="T")


def test_missing_api_key(input_files):
    """Missing OPENAI_API_KEY raises EnvironmentError before any API call."""
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(EnvironmentError):
            run(base_dir=input_files, topic="T")


def test_short_id_format():
    """generate_short_id returns a 5-character alphanumeric string."""
    id_ = generate_short_id()
    assert len(id_) == 5
    assert id_.isalnum()


def test_short_id_uniqueness():
    """Consecutive calls to generate_short_id return different values."""
    ids = {generate_short_id() for _ in range(20)}
    assert len(ids) > 1


def test_openai_error_propagates(input_files):
    """An OpenAI API error propagates as OpenAIError."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = openai.OpenAIError("api failure")
    with patch("writer.writer.openai.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with pytest.raises(openai.OpenAIError):
            run(base_dir=input_files, topic="T")


def test_accent_fallback(input_files):
    """When HTML has no --accent, accent defaults to #5b5ef4."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="<h1>No style</h1>"))]
    )
    with patch("writer.writer.openai.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run(base_dir=input_files, topic="T")

    assert result["accent"] == "#5b5ef4"


def test_title_fallback(input_files):
    """When HTML has no h1, title defaults to 'New Article'."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="<p>No heading</p>"))]
    )
    with patch("writer.writer.openai.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        result = run(base_dir=input_files, topic="T")

    assert result["title"] == "New Article"
