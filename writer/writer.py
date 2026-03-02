import os
import random
import string
import sys
from pathlib import Path

import openai
from rich.console import Console

WRITER_DIR = Path(__file__).parent
REPO_DIR   = WRITER_DIR.parent

console = Console()
err_console = Console(stderr=True)


def generate_short_id(length: int = 5) -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=length))


def _read_file(path: Path) -> str:
    if not path.exists():
        err_console.print(f"[red]Error:[/red] required file not found: {path}")
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def run(base_dir: Path = WRITER_DIR, docs_dir: Path = None) -> None:
    if docs_dir is None:
        docs_dir = REPO_DIR / "docs"

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        err_console.print("[red]Error:[/red] OPENAI_API_KEY environment variable is not set.")
        sys.exit(1)

    inputs = {
        "instructions": base_dir / "inputs" / "instructions.md",
        "topic":        base_dir / "inputs" / "topic.md",
        "history":      base_dir / "inputs" / "history.md",
    }

    console.print("[dim]Reading inputs...[/dim]")
    instructions = _read_file(inputs["instructions"])
    topic        = _read_file(inputs["topic"])
    history      = _read_file(inputs["history"])

    system_message = instructions
    user_message   = f"--- TOPIC ---\n{topic}\n\n--- HISTORY ---\n{history}"

    client = openai.OpenAI(api_key=api_key)
    try:
        with console.status("[bold]Calling gpt-4o...[/bold]", spinner="dots"):
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user",   "content": user_message},
                ],
            )
    except openai.OpenAIError as e:
        err_console.print(f"[red]Error:[/red] OpenAI API call failed: {e}")
        sys.exit(1)

    html = response.choices[0].message.content

    docs_dir.mkdir(exist_ok=True)
    output_path = docs_dir / f"{generate_short_id()}.html"

    console.print(f"[dim]Writing {output_path}...[/dim]")
    output_path.write_text(html, encoding="utf-8")

    console.print(f"[green]✓[/green] {output_path}")
    print(output_path)


if __name__ == "__main__":
    run()
