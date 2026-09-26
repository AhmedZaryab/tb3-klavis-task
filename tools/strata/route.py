"""Fixed router for the strata-index task.

Walks an agent-authored index tree (servers -> groups -> tools) and routes a
natural-language intent to exactly one (server, tool) pair using BM25 over a
single shared tokenizer. The same tokenizer is used for scoring and for
counting tokens read, so there is no tokenizer-mismatch exploit: whatever the
agent pays for in the index, the router reads the same way.

CLI:
    python route.py --index index.json --catalog catalog.json --intent "..."

Library:
    route_intent(index, catalog, intent) -> dict
    validate_index(index, catalog) -> None (raises RouteError)
"""

import argparse
import json
import math
import re
import sys

MAX_SUMMARY_TOKENS = 40
TOKEN_RE = re.compile(r"[a-z0-9]+")

BM25_K1 = 1.5
BM25_B = 0.75


class RouteError(Exception):
    """Raised for any malformed index, unknown tool, or budget violation."""


def tokenize(text):
    """Lowercase, split on non-alphanumerics, no stemming."""
    if not isinstance(text, str):
        raise RouteError(f"expected a string to tokenize, got {type(text).__name__}")
    return TOKEN_RE.findall(text.lower())


def _bm25_scores(query_tokens, doc_token_lists):
    """Score each document in doc_token_lists against query_tokens.

    Standard Okapi BM25, with document-frequency statistics computed over the
    sibling set being compared (the only corpus available at each step of the
    walk). Returns a list of scores, one per document, same order as input.
    """
    n = len(doc_token_lists)
    if n == 0:
        return []

    doc_len = [len(toks) for toks in doc_token_lists]
    avgdl = sum(doc_len) / n if n else 0.0

    df = {}
    for toks in doc_token_lists:
        for term in set(toks):
            df[term] = df.get(term, 0) + 1

    idf = {}
    for term in set(query_tokens):
        n_t = df.get(term, 0)
        idf[term] = math.log((n - n_t + 0.5) / (n_t + 0.5) + 1)

    scores = []
    for toks, dl in zip(doc_token_lists, doc_len):
        tf = {}
        for term in toks:
            tf[term] = tf.get(term, 0) + 1
        score = 0.0
        for term in query_tokens:
            f = tf.get(term, 0)
            if f == 0:
                continue
            denom = f + BM25_K1 * (1 - BM25_B + BM25_B * (dl / avgdl if avgdl else 0.0))
            score += idf[term] * (f * (BM25_K1 + 1)) / denom
        scores.append(score)
    return scores


def _best_index(scores):
    """Deterministic argmax: first index wins ties."""
    best_i = 0
    best_score = scores[0]
    for i in range(1, len(scores)):
        if scores[i] > best_score:
            best_score = scores[i]
            best_i = i
    return best_i


def _require(cond, message):
    if not cond:
        raise RouteError(message)


def _check_summary(summary, where):
    _require(isinstance(summary, str) and summary.strip(), f"{where}: summary must be a non-empty string")
    n = len(tokenize(summary))
    _require(n <= MAX_SUMMARY_TOKENS, f"{where}: summary is {n} tokens, exceeds the {MAX_SUMMARY_TOKENS}-token limit")


def _catalog_index(catalog):
    """Build {(server, tool): entry} from the catalog for membership checks."""
    lookup = {}
    for entry in catalog:
        _require(isinstance(entry, dict) and "server" in entry and "name" in entry,
                  "catalog: every entry needs 'server' and 'name'")
        lookup[(entry["server"], entry["name"])] = entry
    return lookup


def validate_index(index, catalog):
    """Validate structure, summary lengths, and tool membership.

    Raises RouteError with a specific message on the first problem found.
    Does not compute any scores or tokens-read; that happens during the walk.
    """
    _require(isinstance(index, dict), "index: top level must be an object")
    _require("servers" in index and isinstance(index["servers"], list) and index["servers"],
              "index: missing or empty 'servers' list")

    catalog_lookup = _catalog_index(catalog)
    catalog_servers = {s for s, _ in catalog_lookup}

    for s_i, server in enumerate(index["servers"]):
        where = f"servers[{s_i}]"
        _require(isinstance(server, dict), f"{where}: must be an object")
        _require("name" in server and isinstance(server["name"], str), f"{where}: missing 'name'")
        _check_summary(server.get("summary"), f"{where} ({server.get('name')})")
        _require(server["name"] in catalog_servers, f"{where}: unknown server '{server['name']}' not in catalog")
        _require("groups" in server and isinstance(server["groups"], list) and server["groups"],
                  f"{where} ({server['name']}): missing or empty 'groups'")

        for g_i, group in enumerate(server["groups"]):
            gwhere = f"{where}.groups[{g_i}]"
            _require(isinstance(group, dict), f"{gwhere}: must be an object")
            _require("name" in group and isinstance(group["name"], str), f"{gwhere}: missing 'name'")
            _check_summary(group.get("summary"), f"{gwhere} ({group.get('name')})")
            _require("tools" in group and isinstance(group["tools"], list) and group["tools"],
                      f"{gwhere} ({group['name']}): missing or empty 'tools'")

            for t_i, tool in enumerate(group["tools"]):
                twhere = f"{gwhere}.tools[{t_i}]"
                _require(isinstance(tool, dict), f"{twhere}: must be an object")
                _require("name" in tool and isinstance(tool["name"], str), f"{twhere}: missing 'name'")
                _check_summary(tool.get("summary"), f"{twhere} ({tool.get('name')})")
                key = (server["name"], tool["name"])
                _require(key in catalog_lookup,
                          f"{twhere}: tool '{tool['name']}' is not in the catalog for server '{server['name']}'")


def route_intent(index, catalog, intent):
    """Walk the index for one intent. Returns a result dict on success.

    Raises RouteError on any malformed index / unknown tool / bad intent.
    The caller (metrics.py, or the CLI) treats a raised RouteError as a
    failed route, per the verifier's contract.
    """
    _require(isinstance(intent, str) and intent.strip(), "intent must be a non-empty string")
    validate_index(index, catalog)

    query_tokens = tokenize(intent)
    tokens_read = 0

    servers = index["servers"]
    server_summaries = [tokenize(s["summary"]) for s in servers]
    tokens_read += sum(len(t) for t in server_summaries)
    s_scores = _bm25_scores(query_tokens, server_summaries)
    server = servers[_best_index(s_scores)]

    groups = server["groups"]
    group_summaries = [tokenize(g["summary"]) for g in groups]
    tokens_read += sum(len(t) for t in group_summaries)
    g_scores = _bm25_scores(query_tokens, group_summaries)
    group = groups[_best_index(g_scores)]

    tools = group["tools"]
    tool_summaries = [tokenize(t["summary"]) for t in tools]
    tokens_read += sum(len(t) for t in tool_summaries)
    t_scores = _bm25_scores(query_tokens, tool_summaries)
    tool = tools[_best_index(t_scores)]

    return {
        "server": server["name"],
        "tool": tool["name"],
        "tokens_read": tokens_read,
    }


def index_size_tokens(index):
    """Total tokens across every summary in the whole index tree."""
    total = 0
    for server in index.get("servers", []):
        total += len(tokenize(server.get("summary", "")))
        for group in server.get("groups", []):
            total += len(tokenize(group.get("summary", "")))
            for tool in group.get("tools", []):
                total += len(tokenize(tool.get("summary", "")))
    return total


def _load_json(path, label):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise RouteError(f"could not read {label} '{path}': {e}")


def main():
    parser = argparse.ArgumentParser(description="Route one intent through an index.json.")
    parser.add_argument("--index", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--intent", required=True)
    args = parser.parse_args()

    try:
        index = _load_json(args.index, "index")
        catalog = _load_json(args.catalog, "catalog")
        result = route_intent(index, catalog, args.intent)
    except RouteError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
