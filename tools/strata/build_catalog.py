"""Generate catalog.json: ~250 realistic MCP tools across ~22 servers.

Deterministic (seed 0). Near-duplicate tool families (create_issue,
send_message, search_* variants, and cross-server list/get/update/delete
pairs on shared resource nouns like issue/ticket/file/message) are
hand-shaped below, not templated, so their descriptions read like real
MCP servers wrote them independently rather than from one template.

Run: python build_catalog.py > catalog.json
"""

import json
import random

SEED = 0

# ---------------------------------------------------------------------------
# Server registry. Resources reused across servers (issue, ticket, file,
# message, event, query, table, incident, project, customer) are what create
# the near-duplicate families the router has to tell apart.
# ---------------------------------------------------------------------------

SERVERS = {
    "github": {
        "summary": "Source control, issues, and pull requests on GitHub.",
        "resources": {
            "issue": ["get", "list", "update", "delete"],  # create is hand-shaped
            "pull_request": ["create", "get", "list", "update"],
            "repository": ["get", "list"],
            "branch": ["create", "list", "delete"],
            "release": ["create", "get", "list"],
            "label": ["create", "list", "delete"],
        },
    },
    "gitlab": {
        "summary": "Repository hosting, merge requests, and CI pipelines on GitLab.",
        "resources": {
            "issue": ["get", "list", "update", "delete"],
            "merge_request": ["create", "get", "list", "update"],
            "project": ["get", "list"],
            "branch": ["create", "list", "delete"],
            "pipeline": ["get", "list", "create"],
            "label": ["create", "list"],
        },
    },
    "linear": {
        "summary": "Issue tracking and cycle planning for software teams.",
        "resources": {
            "issue": ["get", "list", "update", "delete"],
            "project": ["create", "get", "list", "update"],
            "cycle": ["get", "list"],
            "team": ["get", "list"],
            "comment": ["create", "list"],
        },
    },
    "jira": {
        "summary": "Issue and project tracking for agile software teams.",
        "resources": {
            "issue": ["get", "list", "update", "delete"],
            "project": ["get", "list"],
            "sprint": ["create", "get", "list", "update"],
            "board": ["get", "list"],
            "worklog": ["create", "list"],
        },
    },
    "notion": {
        "summary": "Pages, databases, and blocks in a Notion workspace.",
        "resources": {
            "page": ["create", "get", "list", "update", "delete"],
            "database": ["create", "get", "list", "update"],
            "block": ["get", "list", "update", "delete"],
            "comment": ["create", "list"],
        },
    },
    "confluence": {
        "summary": "Wiki pages and spaces for team documentation in Confluence.",
        "resources": {
            "page": ["create", "get", "list", "update", "delete"],
            "space": ["get", "list"],
            "attachment": ["create", "list", "delete"],
            "comment": ["create", "list"],
        },
    },
    "slack": {
        "summary": "Channels, messages, and users in a Slack workspace.",
        "resources": {
            "message": ["get", "list", "update", "delete"],  # send is hand-shaped
            "channel": ["create", "get", "list"],
            "user": ["get", "list"],
            "file": ["create", "list", "delete"],
            "reminder": ["create", "list", "delete"],
        },
    },
    "discord": {
        "summary": "Servers, channels, and messages on Discord.",
        "resources": {
            "message": ["get", "list", "delete"],  # send is hand-shaped
            "channel": ["create", "get", "list", "delete"],
            "guild": ["get", "list"],
            "role": ["create", "list", "delete"],
            "member": ["get", "list", "update"],
        },
    },
    "gmail": {
        "summary": "Email messages, threads, and labels in a Gmail account.",
        "resources": {
            "message": ["get", "list", "delete"],  # send is hand-shaped
            "thread": ["get", "list"],
            "label": ["create", "list", "delete"],
            "draft": ["create", "get", "list", "delete"],
        },
    },
    "google-calendar": {
        "summary": "Calendars and events in Google Calendar.",
        "resources": {
            "event": ["create", "get", "list", "update", "delete"],
            "calendar": ["get", "list"],
            "attendee": ["update"],
        },
    },
    "google-drive": {
        "summary": "Files, folders, and sharing permissions in Google Drive.",
        "resources": {
            "file": ["create", "get", "list", "update", "delete"],
            "folder": ["create", "get", "list"],
            "permission": ["create", "list", "delete"],
        },
    },
    "dropbox": {
        "summary": "File storage, sharing, and sync for Dropbox accounts.",
        "resources": {
            "file": ["create", "get", "list", "delete"],
            "folder": ["create", "get", "list", "delete"],
            "shared_link": ["create", "list", "delete"],
        },
    },
    "stripe": {
        "summary": "Payments, customers, and subscriptions on Stripe.",
        "resources": {
            "customer": ["create", "get", "list", "update", "delete"],
            "charge": ["create", "get", "list"],
            "invoice": ["create", "get", "list", "update"],
            "subscription": ["create", "get", "list", "update", "delete"],
            "refund": ["create", "get", "list"],
        },
    },
    "shopify": {
        "summary": "Products, orders, and customers for a Shopify store.",
        "resources": {
            "product": ["create", "get", "list", "update", "delete"],
            "order": ["get", "list", "update"],
            "customer": ["create", "get", "list", "update"],
            "inventory_item": ["get", "list", "update"],
            "collection": ["create", "get", "list"],
        },
    },
    "hubspot": {
        "summary": "Contacts, deals, and companies in a HubSpot CRM.",
        "resources": {
            "contact": ["create", "get", "list", "update", "delete"],
            "deal": ["create", "get", "list", "update"],
            "company": ["create", "get", "list", "update"],
            "ticket": ["create", "get", "list", "update"],
            "note": ["create", "list"],
        },
    },
    "salesforce": {
        "summary": "Leads, opportunities, and accounts in Salesforce.",
        "resources": {
            "lead": ["create", "get", "list", "update", "delete"],
            "opportunity": ["create", "get", "list", "update"],
            "account": ["create", "get", "list", "update"],
            "contact": ["create", "get", "list", "update"],
            "case": ["create", "get", "list", "update"],
        },
    },
    "postgres": {
        "summary": "Query execution and schema inspection for a Postgres database.",
        "resources": {
            "query": ["create"],
            "table": ["get", "list"],
            "schema": ["get", "list"],
            "index": ["create", "list", "delete"],
        },
    },
    "snowflake": {
        "summary": "Query execution and warehouse management for Snowflake.",
        "resources": {
            "query": ["create"],
            "table": ["get", "list"],
            "warehouse": ["get", "list", "update"],
            "database": ["get", "list"],
            "stage": ["create", "list"],
        },
    },
    "sentry": {
        "summary": "Error tracking, issues, and alerts across Sentry projects.",
        "resources": {
            "issue": ["get", "list", "update"],
            "event": ["get", "list"],
            "project": ["get", "list"],
            "alert": ["create", "get", "list", "update", "delete"],
        },
    },
    "datadog": {
        "summary": "Monitors, dashboards, and metrics for Datadog observability.",
        "resources": {
            "monitor": ["create", "get", "list", "update", "delete"],
            "dashboard": ["create", "get", "list"],
            "metric": ["get", "list"],
            "incident": ["create", "get", "list", "update"],
            "log": ["get", "list"],
        },
    },
    "pagerduty": {
        "summary": "On-call schedules and incident response for PagerDuty.",
        "resources": {
            "incident": ["create", "get", "list", "update"],
            "service": ["get", "list", "update"],
            "escalation_policy": ["get", "list"],
            "oncall": ["get", "list"],
        },
    },
    "zendesk": {
        "summary": "Support tickets and customers for a Zendesk help desk.",
        "resources": {
            "ticket": ["create", "get", "list", "update", "delete"],
            "user": ["create", "get", "list", "update"],
            "organization": ["get", "list"],
            "macro": ["get", "list"],
        },
    },
}

# ---------------------------------------------------------------------------
# Field pools per resource noun, used to build realistic-ish input schemas.
# ---------------------------------------------------------------------------

FIELD_POOLS = {
    "issue": [("title", "string"), ("description", "string"), ("labels", "array"),
              ("assignee", "string"), ("priority", "string"), ("status", "string"),
              ("milestone", "string")],
    "pull_request": [("title", "string"), ("head_branch", "string"), ("base_branch", "string"),
                      ("body", "string"), ("draft", "boolean"), ("reviewers", "array")],
    "merge_request": [("title", "string"), ("source_branch", "string"), ("target_branch", "string"),
                       ("description", "string"), ("draft", "boolean")],
    "repository": [("name", "string"), ("visibility", "string"), ("description", "string")],
    "project": [("name", "string"), ("description", "string"), ("team_id", "string"),
                ("lead", "string"), ("visibility", "string")],
    "branch": [("name", "string"), ("ref", "string")],
    "release": [("tag_name", "string"), ("name", "string"), ("body", "string"), ("draft", "boolean")],
    "label": [("name", "string"), ("color", "string"), ("description", "string")],
    "cycle": [("name", "string"), ("starts_at", "string"), ("ends_at", "string")],
    "team": [("name", "string"), ("key", "string")],
    "comment": [("body", "string"), ("parent_id", "string")],
    "sprint": [("name", "string"), ("start_date", "string"), ("end_date", "string"), ("goal", "string")],
    "board": [("name", "string"), ("project_id", "string")],
    "worklog": [("time_spent_seconds", "integer"), ("comment", "string"), ("started", "string")],
    "page": [("title", "string"), ("content", "string"), ("parent_id", "string"), ("space_id", "string")],
    "database": [("title", "string"), ("parent_id", "string"), ("properties", "object")],
    "block": [("content", "string"), ("type", "string")],
    "space": [("name", "string"), ("key", "string")],
    "attachment": [("file_path", "string"), ("filename", "string")],
    "message": [("text", "string"), ("channel", "string"), ("recipient", "string"),
                ("thread_id", "string"), ("attachments", "array")],
    "channel": [("name", "string"), ("topic", "string"), ("private", "boolean")],
    "user": [("email", "string"), ("name", "string"), ("role", "string")],
    "file": [("name", "string"), ("parent_id", "string"), ("content", "string"), ("mime_type", "string")],
    "reminder": [("text", "string"), ("time", "string")],
    "guild": [("name", "string")],
    "role": [("name", "string"), ("permissions", "array"), ("color", "string")],
    "member": [("nickname", "string"), ("roles", "array")],
    "thread": [("subject", "string")],
    "draft": [("to", "string"), ("subject", "string"), ("body", "string")],
    "event": [("title", "string"), ("start_time", "string"), ("end_time", "string"),
              ("attendees", "array"), ("location", "string")],
    "calendar": [("name", "string"), ("timezone", "string")],
    "attendee": [("email", "string"), ("response_status", "string")],
    "folder": [("name", "string"), ("parent_id", "string")],
    "permission": [("role", "string"), ("email", "string"), ("type", "string")],
    "shared_link": [("path", "string"), ("visibility", "string")],
    "customer": [("email", "string"), ("name", "string"), ("phone", "string"), ("metadata", "object")],
    "charge": [("amount", "integer"), ("currency", "string"), ("customer_id", "string"), ("description", "string")],
    "invoice": [("customer_id", "string"), ("due_date", "string"), ("line_items", "array")],
    "subscription": [("customer_id", "string"), ("plan_id", "string"), ("quantity", "integer")],
    "refund": [("charge_id", "string"), ("amount", "integer"), ("reason", "string")],
    "product": [("title", "string"), ("description", "string"), ("price", "number"), ("tags", "array")],
    "order": [("status", "string"), ("fulfillment_status", "string")],
    "inventory_item": [("sku", "string"), ("quantity", "integer"), ("location_id", "string")],
    "collection": [("title", "string"), ("rules", "array")],
    "contact": [("email", "string"), ("first_name", "string"), ("last_name", "string"), ("company", "string")],
    "deal": [("name", "string"), ("amount", "number"), ("stage", "string"), ("pipeline_id", "string")],
    "company": [("name", "string"), ("domain", "string"), ("industry", "string")],
    "ticket": [("subject", "string"), ("description", "string"), ("priority", "string"),
               ("requester_email", "string"), ("tags", "array")],
    "note": [("body", "string"), ("associated_object_id", "string")],
    "lead": [("email", "string"), ("company", "string"), ("status", "string")],
    "opportunity": [("name", "string"), ("stage", "string"), ("amount", "number"), ("close_date", "string")],
    "account": [("name", "string"), ("industry", "string"), ("website", "string")],
    "case": [("subject", "string"), ("description", "string"), ("priority", "string"), ("status", "string")],
    "query": [("sql", "string"), ("parameters", "array"), ("timeout_ms", "integer")],
    "table": [("name", "string"), ("schema", "string")],
    "schema": [("name", "string")],
    "index": [("name", "string"), ("table", "string"), ("columns", "array")],
    "warehouse": [("name", "string"), ("size", "string")],
    "stage": [("name", "string"), ("url", "string")],
    "event_sentry": [("project_id", "string")],
    "alert": [("name", "string"), ("conditions", "array"), ("project_id", "string")],
    "monitor": [("name", "string"), ("query", "string"), ("tags", "array"), ("thresholds", "object")],
    "dashboard": [("title", "string"), ("widgets", "array")],
    "metric": [("name", "string"), ("query", "string")],
    "incident": [("title", "string"), ("service_id", "string"), ("urgency", "string"), ("status", "string")],
    "log": [("query", "string"), ("from_time", "string"), ("to_time", "string")],
    "service": [("name", "string"), ("escalation_policy_id", "string")],
    "escalation_policy": [("name", "string")],
    "oncall": [("schedule_id", "string")],
    "organization": [("name", "string")],
    "macro": [("title", "string"), ("actions", "array")],
}

ID_FIELD = {"type": "string", "description": "Unique identifier of the resource."}

ACTION_VERB = {
    "create": ["Create", "Add"],
    "get": ["Fetch", "Retrieve", "Get", "Look up"],
    "list": ["List", "Enumerate", "Return a page of"],
    "update": ["Update", "Modify", "Edit"],
    "delete": ["Delete", "Remove", "Archive"],
}

# resources where "open"/"start" reads more naturally than "create"
_OPENABLE_CREATE_VERBS = ["Open", "Create", "Add"]
_OPENABLE_RESOURCES = {"issue", "ticket", "incident", "case"}

ACTION_TAIL = {
    "create": ["in {server}.", "within the connected {server} account.", "for the workspace."],
    "get": ["by its identifier.", "including its current fields.", "from {server}."],
    "list": ["matching optional filters, paginated.", "visible to the authenticated user.", "ordered by most recent first."],
    "update": ["identified by id, applying only the fields provided.", "in place; unspecified fields are left unchanged."],
    "delete": ["permanently; this cannot be undone.", "identified by id."],
}


def resource_noun(resource: str) -> str:
    return resource.replace("_", " ")


def plural(word: str) -> str:
    if word.endswith("y") and word[-2:-1] not in "aeiou":
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "ch")):
        return word + "es"
    return word + "s"


def build_schema(rng: random.Random, resource: str, action: str) -> dict:
    fields = FIELD_POOLS.get(resource, [("name", "string")])
    fields = list(fields)
    rng.shuffle(fields)

    props = {}
    required = []

    if action in ("get", "update", "delete"):
        props["id"] = dict(ID_FIELD)
        required.append("id")

    if action == "create":
        n = min(len(fields), rng.randint(2, 4))
        chosen = fields[:n]
        for i, (name, typ) in enumerate(chosen):
            props[name] = _schema_type(typ, name)
            if i < 2:
                required.append(name)
    elif action == "update":
        n = min(len(fields), rng.randint(1, 3))
        for name, typ in fields[:n]:
            props[name] = _schema_type(typ, name)
    elif action == "get":
        props["fields"] = {"type": "array", "items": {"type": "string"},
                            "description": "Optional subset of fields to include in the response."}
    elif action == "list":
        props["limit"] = {"type": "integer", "description": "Maximum number of results to return."}
        props["cursor"] = {"type": "string", "description": "Opaque pagination cursor from a previous call."}
        n = min(len(fields), rng.randint(0, 2))
        for name, typ in fields[:n]:
            props[name] = _schema_type(typ, name)
    elif action == "delete":
        props["force"] = {"type": "boolean", "description": "Skip confirmation and delete immediately."}

    if len(props) < 2:
        props["notes"] = {"type": "string", "description": "Free-form context for the operation."}

    return {"type": "object", "properties": props, "required": required}


def _schema_type(typ: str, name: str) -> dict:
    if typ == "array":
        return {"type": "array", "items": {"type": "string"}, "description": f"List of {name.replace('_', ' ')}."}
    if typ == "object":
        return {"type": "object", "description": f"Structured {name.replace('_', ' ')} payload."}
    return {"type": typ, "description": f"The {name.replace('_', ' ')}."}


def build_description(rng: random.Random, server: str, resource: str, action: str) -> str:
    noun = resource_noun(resource)
    if action == "create" and resource in _OPENABLE_RESOURCES:
        verb = rng.choice(_OPENABLE_CREATE_VERBS)
    else:
        verb = rng.choice(ACTION_VERB[action])
    tail = rng.choice(ACTION_TAIL[action]).format(server=server)
    if action == "list":
        subject = plural(noun)
        sentence = f"{verb} {subject} {tail}"
    else:
        article = "an" if noun[0] in "aeiou" else "a"
        sentence = f"{verb} {article} {noun} {tail}"
    sentence = sentence[0].upper() + sentence[1:]

    extra = None
    if action == "create":
        extra = rng.choice([
            "Returns the newly created record.",
            "The caller must have write access to the parent resource.",
            None, None,
        ])
    elif action == "list":
        extra = rng.choice([
            "Results are paginated; use the returned cursor to fetch the next page.",
            None, None,
        ])
    elif action == "delete":
        extra = rng.choice([
            "Related records may be cascade-deleted depending on account settings.",
            None, None,
        ])

    if extra:
        sentence = sentence + " " + extra
    return sentence


# Resources central to the near-duplicate families keep their full action
# set; everything else is capped so the catalog lands near ~250 tools
# instead of ~330, matching what a mid-size MCP fleet actually looks like.
_KEEP_FULL = {"issue", "message", "ticket", "contact", "file", "event"}
_MAX_ACTIONS = 2


def _trimmed_resources(resources: dict) -> dict:
    trimmed = {}
    for resource, actions in resources.items():
        if resource in _KEEP_FULL or len(actions) <= _MAX_ACTIONS:
            trimmed[resource] = actions
        else:
            trimmed[resource] = actions[:_MAX_ACTIONS]
    return trimmed


def generate_generic(rng: random.Random) -> list:
    tools = []
    for server, cfg in SERVERS.items():
        for resource, actions in _trimmed_resources(cfg["resources"]).items():
            for action in actions:
                name = f"{action}_{plural(resource) if action == 'list' else resource}"
                tools.append({
                    "server": server,
                    "name": name,
                    "description": build_description(rng, server, resource, action),
                    "input_schema": build_schema(rng, resource, action),
                })
    return tools


# ---------------------------------------------------------------------------
# Hand-shaped near-duplicate families. These override/extend the generic
# output for the tools a router genuinely has to disambiguate: same verb,
# different platform semantics, written the way each vendor's docs actually
# phrase it (not from one shared template).
# ---------------------------------------------------------------------------

HAND_SHAPED = [
    {
        "server": "github", "name": "create_issue",
        "description": "Open a new issue on a repository. Supports assigning labels, "
                        "one or more assignees, and a milestone at creation time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository in owner/name form."},
                "title": {"type": "string", "description": "Issue title."},
                "body": {"type": "string", "description": "Issue body in Markdown."},
                "labels": {"type": "array", "items": {"type": "string"}, "description": "Labels to apply."},
                "assignees": {"type": "array", "items": {"type": "string"}, "description": "GitHub usernames to assign."},
            },
            "required": ["repo", "title"],
        },
    },
    {
        "server": "gitlab", "name": "create_issue",
        "description": "Create an issue within a project. Accepts an optional milestone "
                        "and weight, and can link the issue to an existing epic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Numeric or path-qualified project id."},
                "title": {"type": "string", "description": "Issue title."},
                "description": {"type": "string", "description": "Issue description in GitLab Flavored Markdown."},
                "milestone_id": {"type": "string", "description": "Milestone to attach the issue to."},
                "weight": {"type": "integer", "description": "Relative effort weight."},
            },
            "required": ["project_id", "title"],
        },
    },
    {
        "server": "linear", "name": "create_issue",
        "description": "Create a new issue on a team, optionally placing it in the "
                        "active cycle and setting a priority from 0 (none) to 4 (urgent).",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "string", "description": "Team the issue belongs to."},
                "title": {"type": "string", "description": "Issue title."},
                "description": {"type": "string", "description": "Issue description in Markdown."},
                "priority": {"type": "integer", "description": "Priority from 0 (none) to 4 (urgent)."},
                "cycle_id": {"type": "string", "description": "Cycle to schedule the issue into."},
            },
            "required": ["team_id", "title"],
        },
    },
    {
        "server": "jira", "name": "create_issue",
        "description": "Create an issue in a project using a specific issue type "
                        "(e.g. Bug, Story, Task) and any custom fields the project schema requires.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_key": {"type": "string", "description": "Project key, e.g. ENG."},
                "issue_type": {"type": "string", "description": "Issue type name, e.g. Bug or Story."},
                "summary": {"type": "string", "description": "One-line issue summary."},
                "description": {"type": "string", "description": "Full issue description."},
                "fields": {"type": "object", "description": "Additional custom field values keyed by field id."},
            },
            "required": ["project_key", "issue_type", "summary"],
        },
    },
    {
        "server": "slack", "name": "send_message",
        "description": "Post a message to a channel or direct message. Supports Slack "
                        "mrkdwn formatting and optional threading via thread_ts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel id or name to post to."},
                "text": {"type": "string", "description": "Message text in Slack mrkdwn."},
                "thread_ts": {"type": "string", "description": "Timestamp of a parent message to reply in-thread."},
            },
            "required": ["channel", "text"],
        },
    },
    {
        "server": "discord", "name": "send_message",
        "description": "Send a message to a text channel. Accepts plain content and up "
                        "to 10 embed objects, but does not support threaded replies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel_id": {"type": "string", "description": "Snowflake id of the target channel."},
                "content": {"type": "string", "description": "Plain text message content."},
                "embeds": {"type": "array", "items": {"type": "object"}, "description": "Rich embed objects, max 10."},
            },
            "required": ["channel_id", "content"],
        },
    },
    {
        "server": "gmail", "name": "send_message",
        "description": "Send an email from the authenticated account. The message is "
                        "composed as MIME and delivered immediately; it is not saved as a draft first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address."},
                "subject": {"type": "string", "description": "Email subject line."},
                "body": {"type": "string", "description": "Plain text or HTML email body."},
                "cc": {"type": "string", "description": "Comma-separated CC recipients."},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "server": "github", "name": "search_issues",
        "description": "Search issues and pull requests across repositories using "
                        "GitHub's issue search qualifier syntax (e.g. is:open label:bug).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "GitHub search syntax, e.g. 'is:open label:bug repo:org/name'."},
                "sort": {"type": "string", "description": "Field to sort by, e.g. created or updated."},
                "limit": {"type": "integer", "description": "Maximum number of results."},
            },
            "required": ["query"],
        },
    },
    {
        "server": "gitlab", "name": "search_issues",
        "description": "Search issues within a project or group by title and description "
                        "text, with optional label and state filters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scope_id": {"type": "string", "description": "Project or group id to search within."},
                "search": {"type": "string", "description": "Free-text search term."},
                "labels": {"type": "array", "items": {"type": "string"}, "description": "Restrict to issues with all of these labels."},
                "state": {"type": "string", "description": "opened, closed, or all."},
            },
            "required": ["scope_id", "search"],
        },
    },
    {
        "server": "linear", "name": "search_issues",
        "description": "Full-text search over issue titles and descriptions across all "
                        "teams the caller can access, ranked by relevance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "term": {"type": "string", "description": "Search term."},
                "team_id": {"type": "string", "description": "Restrict results to a single team."},
                "limit": {"type": "integer", "description": "Maximum number of results."},
            },
            "required": ["term"],
        },
    },
    {
        "server": "jira", "name": "search_issues",
        "description": "Search issues using JQL (Jira Query Language) and return the "
                        "matching issues with the requested fields.",
        "input_schema": {
            "type": "object",
            "properties": {
                "jql": {"type": "string", "description": "JQL query string."},
                "fields": {"type": "array", "items": {"type": "string"}, "description": "Fields to include per issue."},
                "max_results": {"type": "integer", "description": "Maximum number of issues to return."},
            },
            "required": ["jql"],
        },
    },
    {
        "server": "hubspot", "name": "search_contacts",
        "description": "Search contacts by property filters (email, name, lifecycle "
                        "stage) using HubSpot's CRM search API.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text search across default contact properties."},
                "filters": {"type": "array", "items": {"type": "object"}, "description": "Structured property filter groups."},
                "limit": {"type": "integer", "description": "Maximum number of results."},
            },
            "required": ["query"],
        },
    },
    {
        "server": "salesforce", "name": "search_contacts",
        "description": "Run a SOSL search scoped to the Contact object and return "
                        "matching records with the given fields.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_term": {"type": "string", "description": "Term to search for across searchable contact fields."},
                "fields": {"type": "array", "items": {"type": "string"}, "description": "Fields to return per contact."},
            },
            "required": ["search_term"],
        },
    },
    {
        "server": "slack", "name": "search_messages",
        "description": "Search messages across channels the caller has access to, "
                        "using Slack's message search modifiers like from: and in:.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query, supports from:, in:, before:, after: modifiers."},
                "count": {"type": "integer", "description": "Maximum number of results."},
            },
            "required": ["query"],
        },
    },
    {
        "server": "discord", "name": "search_messages",
        "description": "Search message history in a guild by author, mentions, or "
                        "content; unlike Slack this requires a guild_id and is eventually consistent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "guild_id": {"type": "string", "description": "Guild to search within."},
                "content": {"type": "string", "description": "Text to search for in message content."},
                "author_id": {"type": "string", "description": "Restrict results to messages from this user."},
            },
            "required": ["guild_id", "content"],
        },
    },
]


def merge(generic: list, hand_shaped: list) -> list:
    by_key = {(t["server"], t["name"]): t for t in generic}
    for t in hand_shaped:
        by_key[(t["server"], t["name"])] = t
    return list(by_key.values())


def main():
    rng = random.Random(SEED)
    tools = merge(generate_generic(rng), HAND_SHAPED)
    tools.sort(key=lambda t: (t["server"], t["name"]))
    print(json.dumps(tools, indent=2))


if __name__ == "__main__":
    main()
