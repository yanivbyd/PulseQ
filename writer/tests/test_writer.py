import os
import sys
import pytest
import openai
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure the repo root is on the path so we can import writer.writer
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

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

def test_happy_path(input_files, mock_openai, capsys):
    """Valid inputs produce an HTML file in docs/ and print its path."""
    docs = input_files / "docs"
    with patch("writer.writer.openai.OpenAI", return_value=mock_openai), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        run(base_dir=input_files, docs_dir=docs)

    html_files = list(docs.glob("*.html"))
    assert len(html_files) == 1
    assert html_files[0].read_text() == "<html><title>Test</title></html>"

    captured = capsys.readouterr()
    assert str(html_files[0]) in captured.out


def test_missing_instructions(input_files, mock_openai):
    """Missing instructions.md exits non-zero."""
    (input_files / "inputs" / "instructions.md").unlink()
    with patch("writer.writer.openai.OpenAI", return_value=mock_openai), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with pytest.raises(SystemExit) as exc:
            run(base_dir=input_files, docs_dir=input_files / "docs")
    assert exc.value.code != 0


def test_missing_topic(input_files, mock_openai):
    """Missing topic.md exits non-zero."""
    (input_files / "inputs" / "topic.md").unlink()
    with patch("writer.writer.openai.OpenAI", return_value=mock_openai), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with pytest.raises(SystemExit) as exc:
            run(base_dir=input_files, docs_dir=input_files / "docs")
    assert exc.value.code != 0


def test_missing_history(input_files, mock_openai):
    """Missing history.md exits non-zero."""
    (input_files / "inputs" / "history.md").unlink()
    with patch("writer.writer.openai.OpenAI", return_value=mock_openai), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with pytest.raises(SystemExit) as exc:
            run(base_dir=input_files, docs_dir=input_files / "docs")
    assert exc.value.code != 0


def test_missing_api_key(input_files):
    """Missing OPENAI_API_KEY exits non-zero before any API call."""
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(SystemExit) as exc:
            run(base_dir=input_files, docs_dir=input_files / "docs")
    assert exc.value.code != 0


def test_short_id_format():
    """generate_short_id returns a 5-character alphanumeric string."""
    id_ = generate_short_id()
    assert len(id_) == 5
    assert id_.isalnum()


def test_short_id_uniqueness():
    """Consecutive calls to generate_short_id return different values."""
    ids = {generate_short_id() for _ in range(20)}
    assert len(ids) > 1


def test_openai_error_exits(input_files):
    """An OpenAI API error exits non-zero."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = openai.OpenAIError("api failure")
    with patch("writer.writer.openai.OpenAI", return_value=mock_client), \
         patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with pytest.raises(SystemExit) as exc:
            run(base_dir=input_files, docs_dir=input_files / "docs")
    assert exc.value.code != 0
