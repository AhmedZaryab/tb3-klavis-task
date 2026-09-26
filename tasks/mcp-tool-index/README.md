# terminal-bench/mcp-tool-index

Write a compressed index of 242 MCP tools across 22 servers so that a fixed, readable router can send
plain-language requests to the right tool while reading a small token budget. The catalog has deliberate
look-alike families (create_issue on four trackers, send_message on three chat and mail servers, "issue"
meaning a ticket on some servers and an error group on another), so the words chosen for each summary decide
whether the router lands on the right tool.

## Difficulty explanation

The router is fixed and the budgets are tight, so the only lever is which words go into a few thousand
tokens of summaries. Compressing a catalog well means finding, for every tool, the one or two terms that
separate it from its look-alikes on other servers and from its siblings on the same server, and placing them
at the level of the tree where the router will score them. Requests are written by hand in ordinary language
and rarely name the tool, so an index built by checking it against one's own paraphrases tends to encode
that vocabulary rather than the catalog's distinctions; the hidden requests are what expose that.

## Solution explanation

Group each server's tools by their resource noun, write the server summary from its distinctive nouns, and
for every tool that shares a name with tools on other servers, pick the terms present in its description but
absent from its look-alikes' descriptions, then trim each summary to the token budget. The reference index is
built from the catalog alone, never from the graded requests.

## Verification explanation

The verifier runs in its own container with the same router and catalog and a hidden set of hand-written
requests with one labelled tool each. It parses the submitted index, rejects anything that is invalid for the
catalog or over the total budget, routes every hidden request, fails any route that reads more than the
per-route budget, and requires the hit rate to reach the stated bar. No agent code is executed. Reward is 1 or 0.

## Relevant experience

I built an agent gateway that routes 183 tools across 10 products; the cost of exposing every tool definition
on every request is the reason that gateway compresses and routes tool context, which is exactly what this
task asks for.
