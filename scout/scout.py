import json
import logging
import re

import openai

logger = logging.getLogger(__name__)


def build_prompt(instructions: str, user_tastes: str, topics: list, feedback_events: list) -> tuple[str, str]:
    system_prompt = f"{instructions}\n\n## User Taste Profile\n{user_tastes}"

    topics_json = json.dumps(topics, indent=2)
    events_text = (
        "\n".join(json.dumps(e) for e in feedback_events)
        if feedback_events
        else "(none)"
    )
    user_prompt = (
        f"Current topics (JSON):\n{topics_json}\n\n"
        f"Feedback events from the user (each line is a full JSON event; "
        f"use articleTitle for fuzzy matching):\n{events_text}\n\n"
        f'Return a JSON array of 10 topics: [{{"title": "...", "description": "..."}}].\n'
        f"Do not include any topic that matches a read title.\n"
        f"Do not repeat topics already in the current list that are not being removed."
    )
    return system_prompt, user_prompt


def parse_response(content: str) -> list:
    content = content.strip()
    match = re.match(r"^```(?:json)?\n?(.*)\n?```\s*$", content, re.DOTALL | re.IGNORECASE)
    if match:
        content = match.group(1).strip()
    result = json.loads(content)
    if not isinstance(result, list):
        raise ValueError(f"expected a JSON array, got {type(result).__name__}")
    for item in result:
        if not isinstance(item, dict) or "title" not in item or "description" not in item:
            raise ValueError(f"each topic must have 'title' and 'description', got: {item}")
    return result


def run(instructions: str, user_tastes: str, topics: list, feedback_events: list, api_key: str) -> list:
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set.")

    system_prompt, user_prompt = build_prompt(instructions, user_tastes, topics, feedback_events)
    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = response.choices[0].message.content
    try:
        updated_topics = parse_response(raw)
    except Exception as e:
        logger.error("scout: invalid OpenAI response: %s", raw)
        raise
    logger.info("scout: updated topics count=%d", len(updated_topics))
    return updated_topics
