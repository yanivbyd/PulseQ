from writer.workflow_state import WorkflowState

TAVILY_RESULTS = {"results": [{"url": "https://ex.com", "title": "T"}], "images": []}


# ── from_event ────────────────────────────────────────────────────────────────

def test_from_event_all_fields():
    state = WorkflowState.from_event({
        "userId": "u1",
        "articleId": "a1",
        "articleTopic": "topic",
        "customTopic": "ct",
        "followUpArticleId": "fid",
        "extraContent": "ec",
        "tavilyResults": TAVILY_RESULTS,
        "articleTitle": "My Article",
    })
    assert state.userId == "u1"
    assert state.articleId == "a1"
    assert state.articleTopic == "topic"
    assert state.customTopic == "ct"
    assert state.followUpArticleId == "fid"
    assert state.extraContent == "ec"
    assert state.tavilyResults == TAVILY_RESULTS
    assert state.articleTitle == "My Article"


def test_from_event_only_user_id():
    state = WorkflowState.from_event({"userId": "u1"})
    assert state.userId == "u1"
    assert state.articleId is None
    assert state.articleTopic is None
    assert state.customTopic is None
    assert state.followUpArticleId is None
    assert state.extraContent is None
    assert state.tavilyResults is None
    assert state.articleTitle is None


def test_from_event_missing_user_id_returns_empty_string():
    state = WorkflowState.from_event({})
    assert state.userId == ""


# ── to_dict ───────────────────────────────────────────────────────────────────

def test_to_dict_strips_none_optional_fields():
    out = WorkflowState(userId="u1").to_dict()
    assert out == {"userId": "u1"}


def test_to_dict_includes_all_set_fields():
    out = WorkflowState(
        userId="u1",
        articleId="a1",
        articleTopic="topic",
        tavilyResults=TAVILY_RESULTS,
        articleTitle="My Article",
    ).to_dict()
    assert out == {
        "userId": "u1",
        "articleId": "a1",
        "articleTopic": "topic",
        "tavilyResults": TAVILY_RESULTS,
        "articleTitle": "My Article",
    }


def test_to_dict_round_trips_through_from_event():
    original = WorkflowState(
        userId="u1",
        articleId="a1",
        articleTopic="topic",
        followUpArticleId="fid",
        extraContent="ec",
        tavilyResults=TAVILY_RESULTS,
        articleTitle="My Article",
    )
    restored = WorkflowState.from_event(original.to_dict())
    assert restored == original
