"""
Typed workflow state for the writer Step Functions pipeline.

The input subset is mirrored in backend/workflow_input_state.ts — keep in sync when adding initial input fields.

Pipeline: TopicSelector → Tavily → Article → Quiz → Notification
Each Lambda receives and returns a (partial) WorkflowState via from_event / to_dict.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


def _strip_none(d: dict) -> dict:
    """Remove None-valued keys so absent optional fields are omitted from the SFN payload."""
    return {k: v for k, v in d.items() if v is not None}


@dataclass
class WorkflowState:
    # Always present — the PulseQ user the article is generated for.
    userId: str

    # Set by TopicSelector — unique ID for the article being generated.
    articleId: Optional[str] = None

    # Set by TopicSelector — the search prompt and generation seed (e.g. "Load Balancers — Overview").
    articleTopic: Optional[str] = None

    # Optional initial input — caller-supplied topic; overrides random topic selection.
    customTopic: Optional[str] = None

    # Optional initial input — articleId of the original article this follow-up is based on.
    followUpArticleId: Optional[str] = None

    # Optional initial input — additional context or angle for a follow-up article.
    extraContent: Optional[str] = None

    # Set by Tavily — full Tavily search response (results array + images array).
    tavilyResults: Optional[dict] = None

    # Set by Article — final article title extracted from the generated HTML <title> tag.
    articleTitle: Optional[str] = None

    @classmethod
    def from_event(cls, event: dict) -> WorkflowState:
        return cls(
            userId=event.get("userId", ""),
            articleId=event.get("articleId"),
            articleTopic=event.get("articleTopic"),
            customTopic=event.get("customTopic"),
            followUpArticleId=event.get("followUpArticleId"),
            extraContent=event.get("extraContent"),
            tavilyResults=event.get("tavilyResults"),
            articleTitle=event.get("articleTitle"),
        )

    def to_dict(self) -> dict:
        return _strip_none(asdict(self))
