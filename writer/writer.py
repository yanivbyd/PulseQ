import os
import random
import string
from pathlib import Path

import openai


def generate_short_id(length: int = 5) -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=length))


def _read_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"required file not found: {path}")
    return path.read_text(encoding="utf-8")


def run(base_dir: Path, docs_dir: Path) -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY environment variable is not set.")

    instructions = _read_file(base_dir / "inputs" / "instructions.md")
    topic        = _read_file(base_dir / "inputs" / "topic.md")
    history      = _read_file(base_dir / "inputs" / "history.md")

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user",   "content": f"--- TOPIC ---\n{topic}\n\n--- HISTORY ---\n{history}"},
        ],
    )

    html = response.choices[0].message.content
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / f"{generate_short_id()}.html").write_text(html, encoding="utf-8")
