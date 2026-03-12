import json
import logging
import os
import random
import re
import string

import openai

logger = logging.getLogger(__name__)


def generate_short_id(length: int = 5) -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=length))


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


def _validate_quiz(quiz: list) -> None:
    if not isinstance(quiz, list) or not (1 <= len(quiz) <= 2):
        raise ValueError("quiz must be a list of 1-2 items")
    for item in quiz:
        if not isinstance(item.get("q"), str) or not item["q"]:
            raise ValueError("quiz item missing non-empty 'q'")
        options = item.get("options", [])
        answer = item.get("answer")
        if not isinstance(answer, int) or not (0 <= answer < len(options)):
            raise ValueError("quiz item 'answer' must be a valid option index")


def _shuffle_options(quiz: list) -> list:
    for item in quiz:
        correct = item["options"][item["answer"]]
        random.shuffle(item["options"])
        item["answer"] = item["options"].index(correct)
    return quiz


def generate_quiz(client, html: str, quiz_prompt: str) -> list:
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": quiz_prompt},
                {"role": "user",   "content": html},
            ],
        )
        raw = response.choices[0].message.content
        quiz = json.loads(raw)
        _validate_quiz(quiz)
        return _shuffle_options(quiz)
    except Exception as e:
        logger.warning("quiz generation failed: %s", e)
        return []


def generate_follow_up_article(original_html: str, follow_up_extra_context: str, user_tastes: str, instructions: str) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY environment variable is not set.")

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user",   "content": f"--- EXTRA CONTEXT ---\n{follow_up_extra_context}"},
            {"role": "user",   "content": f"--- USER TASTES ---\n{user_tastes}"},
            {"role": "user",   "content": f"--- ORIGINAL ARTICLE ---\n{original_html}"},
        ],
    )

    html = strip_markdown_fences(response.choices[0].message.content)
    return {
        "id": generate_short_id(),
        "html": html,
        "title": _extract_title(html),
        "accent": _extract_accent(html),
    }


def generate_article(topic: str, article_instructions: str, user_tastes: str) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY environment variable is not set.")

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": article_instructions},
            {"role": "user",   "content": f"--- USER TASTES ---\n{user_tastes}"},
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
