import logging
import os
import random
import re
import string
from pathlib import Path

import openai

logger = logging.getLogger(__name__)


def generate_short_id(length: int = 5) -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=length))


def _read_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"required file not found: {path}")
    return path.read_text(encoding="utf-8")


def strip_markdown_fences(text: str) -> str:
    text = text.strip()
    match = re.match(r"^```html\n?(.*)\n?```\s*$", text, re.DOTALL | re.IGNORECASE)
    if match:
        logger.info("stripped markdown fence: ```html{content}```")
        return match.group(1).strip()
    return text


def _extract_title(html: str) -> str:
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else "New Article"


def _extract_accent(html: str) -> str:
    match = re.search(r"--accent:\s*(#[0-9a-fA-F]{3,8})", html)
    return match.group(1) if match else "#5b5ef4"


def run(base_dir: Path, topic: str) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY environment variable is not set.")

    instructions = _read_file(base_dir / "inputs" / "instructions.md")

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user",   "content": f"--- TOPIC ---\n{topic}"},
        ],
    )

    html = strip_markdown_fences(response.choices[0].message.content)
    return {
        "id": generate_short_id(),
        "html": html,
        "title": _extract_title(html),
        "accent": _extract_accent(html),
    }
