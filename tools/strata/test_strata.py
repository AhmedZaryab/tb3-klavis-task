import json

import pytest

import route
from route import RouteError, route_intent, tokenize, validate_index
from metrics import evaluate


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

def test_tokenize_lowercases():
    assert tokenize("Create Issue") == ["create", "issue"]


def test_tokenize_splits_on_non_alphanumerics():
    assert tokenize("api-key_2, please!") == ["api", "key", "2", "please"]


def test_tokenize_splits_underscores_and_punctuation():
    assert tokenize("send_message (v2)") == ["send", "message", "v2"]


def test_tokenize_no_stemming():
    # "running" and "run" must stay distinct tokens: no stemming/lemmatizing.
    assert tokenize("running") != tokenize("run")
    assert tokenize("issues") != tokenize("issue")


def test_tokenize_rejects_non_string():
    with pytest.raises(RouteError):
        tokenize(None)


# ---------------------------------------------------------------------------
# Fixtures: a tiny 3-server catalog + matching index
# ---------------------------------------------------------------------------

def make_catalog():
    return [
        {"server": "github", "name": "create_issue",
         "description": "Open a new issue on a repository.",
         "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}},
        {"server": "github", "name": "list_issues",
         "description": "List issues on a repository.",
         "input_schema": {"type": "object", "properties": {"repo": {"type": "string"}}, "required": ["repo"]}},
        {"server": "slack", "name": "send_message",
         "description": "Post a message to a channel.",
         "input_schema": {"type": "object", "properties": {"channel": {"type": "string"}}, "required": ["channel"]}},
        {"server": "slack", "name": "list_channels",
         "description": "List channels in the workspace.",
         "input_schema": {"type": "object", "properties": {}, "required": []}},
        {"server": "stripe", "name": "create_customer",
         "description": "Create a customer record.",
         "input_schema": {"type": "object", "properties": {"email": {"type": "string"}}, "required": ["email"]}},
        {"server": "stripe", "name": "list_customers",
         "description": "List customer records.",
         "input_schema": {"type": "object", "properties": {}, "required": []}},
    ]


def make_index():
    # Summaries deliberately share exact tokens with the test intents below
    # (the router does no stemming, so "issue" and "issues" are unrelated
    # tokens) and keep the losing sibling's overlap strictly smaller.
    return {
        "servers": [
            {
                "name": "github",
                "summary": "source code repository issue and pull request tools",
                "groups": [
                    {
                        "name": "issues",
                        "summary": "open and list issue on a repository",
                        "tools": [
                            {"name": "create_issue", "summary": "open a new issue on a repository"},
                            {"name": "list_issues", "summary": "list issue history for a repository"},
                        ],
                    }
                ],
            },
            {
                "name": "slack",
                "summary": "team chat channel and message tools",
                "groups": [
                    {
                        "name": "messaging",
                        "summary": "post a message to a channel",
                        "tools": [
                            {"name": "send_message", "summary": "post a message to a channel"},
                            {"name": "list_channels", "summary": "list channels in the workspace"},
                        ],
                    }
                ],
            },
            {
                "name": "stripe",
                "summary": "payment customer and billing record tools",
                "groups": [
                    {
                        "name": "customers",
                        "summary": "create a new customer record",
                        "tools": [
                            {"name": "create_customer", "summary": "create a new customer record"},
                            {"name": "list_customers", "summary": "list customer billing history"},
                        ],
                    }
                ],
            },
        ]
    }


# ---------------------------------------------------------------------------
# End-to-end routing
# ---------------------------------------------------------------------------

def test_end_to_end_routes_obvious_intent_to_github_create_issue():
    catalog = make_catalog()
    index = make_index()
    result = route_intent(index, catalog, "open a new issue on the repository")
    assert (result["server"], result["tool"]) == ("github", "create_issue")


def test_end_to_end_routes_slack_send_message():
    catalog = make_catalog()
    index = make_index()
    result = route_intent(index, catalog, "post a message to a channel")
    assert (result["server"], result["tool"]) == ("slack", "send_message")


def test_end_to_end_routes_stripe_create_customer():
    catalog = make_catalog()
    index = make_index()
    result = route_intent(index, catalog, "create a new customer record")
    assert (result["server"], result["tool"]) == ("stripe", "create_customer")


# ---------------------------------------------------------------------------
# Budget accounting
# ---------------------------------------------------------------------------

def test_tokens_read_equals_sum_of_scored_summaries():
    catalog = make_catalog()
    index = make_index()
    result = route_intent(index, catalog, "open a new issue on the repository")

    server = next(s for s in index["servers"] if s["name"] == result["server"])
    group = server["groups"][0]

    expected = (
        sum(len(tokenize(s["summary"])) for s in index["servers"])
        + sum(len(tokenize(g["summary"])) for g in server["groups"])
        + sum(len(tokenize(t["summary"])) for t in group["tools"])
    )
    assert result["tokens_read"] == expected


def test_tokens_read_only_counts_the_chosen_branch_at_each_level():
    # A 3-server, 1-group-each index: tokens read must be server summaries
    # (all of them) + groups within the winning server (all of them, here 1)
    # + tools within the winning group (all of them) -- never the losing
    # server's groups or tools.
    catalog = make_catalog()
    index = make_index()
    result = route_intent(index, catalog, "post a message to a channel")
    # slack has exactly one group with 2 tools; github/stripe groups+tools
    # must not be counted.
    server_tokens = sum(len(tokenize(s["summary"])) for s in index["servers"])
    slack_group = index["servers"][1]["groups"][0]
    group_tokens = len(tokenize(slack_group["summary"]))
    tool_tokens = sum(len(tokenize(t["summary"])) for t in slack_group["tools"])
    assert result["tokens_read"] == server_tokens + group_tokens + tool_tokens


# ---------------------------------------------------------------------------
# Tie-breaking determinism
# ---------------------------------------------------------------------------

def test_tie_break_picks_first_sibling_deterministically():
    catalog = make_catalog()
    index = make_index()
    # An intent with zero token overlap against any server summary scores
    # 0.0 everywhere -> the router must deterministically pick the first
    # server in document order (github), not something arbitrary.
    intent = "zzz_no_overlap_whatsoever_qqq"
    for _ in range(5):
        result = route_intent(index, catalog, intent)
        assert result["server"] == "github"


def test_tie_break_is_repeatable_across_calls():
    catalog = make_catalog()
    index = make_index()
    results = [route_intent(index, catalog, "list records") for _ in range(10)]
    assert len(set((r["server"], r["tool"]) for r in results)) == 1


# ---------------------------------------------------------------------------
# Rejection of malformed input
# ---------------------------------------------------------------------------

def test_rejects_missing_servers_key():
    with pytest.raises(RouteError):
        validate_index({}, make_catalog())


def test_rejects_empty_servers_list():
    with pytest.raises(RouteError):
        validate_index({"servers": []}, make_catalog())


def test_rejects_summary_over_40_tokens():
    catalog = make_catalog()
    index = make_index()
    index["servers"][0]["summary"] = " ".join(["word"] * 41)
    with pytest.raises(RouteError, match="40-token"):
        validate_index(index, catalog)


def test_accepts_summary_at_exactly_40_tokens():
    catalog = make_catalog()
    index = make_index()
    index["servers"][0]["summary"] = " ".join(["word"] * 40)
    validate_index(index, catalog)  # must not raise


def test_rejects_unknown_tool_name():
    catalog = make_catalog()
    index = make_index()
    index["servers"][0]["groups"][0]["tools"][0]["name"] = "delete_everything"
    with pytest.raises(RouteError, match="not in the catalog"):
        validate_index(index, catalog)


def test_rejects_tool_from_wrong_server():
    # send_message exists in the catalog, but under slack, not github.
    catalog = make_catalog()
    index = make_index()
    index["servers"][0]["groups"][0]["tools"][0]["name"] = "send_message"
    with pytest.raises(RouteError, match="not in the catalog"):
        validate_index(index, catalog)


def test_rejects_unknown_server_name():
    catalog = make_catalog()
    index = make_index()
    index["servers"][0]["name"] = "not_a_real_server"
    with pytest.raises(RouteError, match="unknown server"):
        validate_index(index, catalog)


def test_rejects_missing_groups():
    catalog = make_catalog()
    index = make_index()
    del index["servers"][0]["groups"]
    with pytest.raises(RouteError):
        validate_index(index, catalog)


def test_rejects_empty_intent():
    with pytest.raises(RouteError):
        route_intent(make_index(), make_catalog(), "")


def test_route_intent_raises_on_malformed_index_rather_than_crashing():
    catalog = make_catalog()
    bad_index = {"servers": [{"name": "github", "summary": "x"}]}  # no groups
    with pytest.raises(RouteError):
        route_intent(bad_index, catalog, "open an issue")


# ---------------------------------------------------------------------------
# metrics.evaluate treats route errors as misses, not crashes
# ---------------------------------------------------------------------------

def test_metrics_counts_malformed_route_as_miss_not_crash():
    catalog = make_catalog()
    index = make_index()
    index["servers"][0]["summary"] = " ".join(["word"] * 41)  # now invalid
    intents = [{"intent": "open an issue", "server": "github", "tool": "create_issue"}]
    result = evaluate(index, catalog, intents)
    assert result["num_hits"] == 0
    assert result["hit_rate"] == 0.0
    assert len(result["misses"]) == 1
    assert "error" in result["misses"][0]


def test_metrics_hit_rate_and_index_size_on_valid_index():
    catalog = make_catalog()
    index = make_index()
    intents = [
        {"intent": "open a new issue on the repository", "server": "github", "tool": "create_issue"},
        {"intent": "post a message to a channel", "server": "slack", "tool": "send_message"},
        {"intent": "create a new customer record", "server": "stripe", "tool": "create_customer"},
    ]
    result = evaluate(index, catalog, intents)
    assert result["num_hits"] == 3
    assert result["hit_rate"] == 1.0
    assert result["index_size_tokens"] == route.index_size_tokens(index)


def test_metrics_marks_over_budget_route_as_miss():
    catalog = make_catalog()
    index = make_index()
    intents = [{"intent": "open a new issue on the repository", "server": "github", "tool": "create_issue"}]
    result = evaluate(index, catalog, intents, max_tokens_per_route=1)
    assert result["num_hits"] == 0
    assert result["misses"][0].get("over_budget") is True
    assert result["within_budget"] is False
