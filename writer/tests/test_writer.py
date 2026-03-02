import os
import pytest
import openai
from pathlib import Path
from unittest.mock import patch, MagicMock

from writer.writer import generate_short_id, run


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def input_files(tmp_path):
    """Create all required input files and a docs dir."""
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    docs = tmp_path / "docs"
    docs.mkdir()

    (inputs / "instructions.md").write_text("Style instructions.")
    (inputs / "topic.md").write_text("Topic content.")
    (inputs / "history.md").write_text("## abc12\n- Title: Old Article\n- Match: Good")

    return tmp_path


@pytest.fixture
def mock_openai():
    """Return a mock OpenAI client whose chat completion returns HTML."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="<html><title>Test</title></html>"))]
    )
    return mock_client


# ── Tests ───────────────────────────────────────────────────────────────────

def test_happy_path(input_files, mock_openai):
    """Valid inputs produce an HTML file in docs/."""
    docs = input_files / "docs"
    with patch("writer.writer.openai.OpenAI", return_value=mock_openai), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        run(base_dir=input_files, docs_dir=docs)

    html_files = list(docs.glob("*.html"))
    assert len(html_files) == 1
    assert html_files[0].read_text() == "<html><title>Test</title></html>"


def test_missing_instructions(input_files, mock_openai):
    """Missing instructions.md raises FileNotFoundError."""
    (input_files / "inputs" / "instructions.md").unlink()
    with patch("writer.writer.openai.OpenAI", return_value=mock_openai), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with pytest.raises(FileNotFoundError):
            run(base_dir=input_files, docs_dir=input_files / "docs")


def test_missing_topic(input_files, mock_openai):
    """Missing topic.md raises FileNotFoundError."""
    (input_files / "inputs" / "topic.md").unlink()
    with patch("writer.writer.openai.OpenAI", return_value=mock_openai), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with pytest.raises(FileNotFoundError):
            run(base_dir=input_files, docs_dir=input_files / "docs")


def test_missing_history(input_files, mock_openai):
    """Missing history.md raises FileNotFoundError."""
    (input_files / "inputs" / "history.md").unlink()
    with patch("writer.writer.openai.OpenAI", return_value=mock_openai), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with pytest.raises(FileNotFoundError):
            run(base_dir=input_files, docs_dir=input_files / "docs")


def test_missing_api_key(input_files):
    """Missing OPENAI_API_KEY raises EnvironmentError before any API call."""
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(EnvironmentError):
            run(base_dir=input_files, docs_dir=input_files / "docs")


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
            run(base_dir=input_files, docs_dir=input_files / "docs")
