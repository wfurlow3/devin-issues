import re


def select_relevant_comments(comments: list | None, max_count: int = 3):
    if not comments:
        return []

    keywords = [
        "repro",
        "reproduce",
        "steps",
        "example",
        "curl",
        "snippet",
        "traceback",
        "stack trace",
        "error",
        "failing",
        "regression",
        "bisect",
        "workaround",
        "patch",
        "fix",
        "pr",
    ]

    scored = []
    for c in comments:
        user = c.get("user") or {}
        login = (user.get("login") or "").lower()
        if "bot" in login or user.get("type") == "Bot":
            continue
        body = c.get("body") or ""
        body_lower = body.lower()

        score = 0
        assoc = c.get("author_association")
        if assoc in {"OWNER", "MEMBER", "COLLABORATOR"}:
            score += 5
        if any(k in body_lower for k in keywords):
            score += 3
        if "```" in body or "traceback" in body_lower or "exception" in body_lower:
            score += 2
        if 40 < len(body) < 4000:
            score += 1

        scored.append((score, c))

    scored.sort(
        key=lambda item: (item[0], item[1].get("created_at") or ""),
        reverse=True,
    )

    return [c for _, c in scored[:max_count]]


def _normalize_comment_body(text: str):
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines()]
    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _truncate_comment_body(text: str):
    if not text:
        return ""
    max_len = 800
    if "```" in text or "Traceback" in text:
        max_len = 2000
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
