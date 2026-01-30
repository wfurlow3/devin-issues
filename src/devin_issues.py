import os
import json
import sys
import time
from dotenv import load_dotenv
import requests

API_BASE = "https://api.devin.ai/v1"

def main():
    load_dotenv()
    repo = "psf/requests"
    issues = list_issues(repo)
    if not issues:
        return

    choice = input("\nSelect an issue to analyze by index (1-20): ").strip()

    if choice[0] == "#":
        raise ValueError("Provide issue by list index, not issue number")
    if not choice.isdigit():
        print("Invalid input.")
        return
    idx = int(choice) - 1
    if idx < 0 or idx >= len(issues):
        print("Selection out of range.")
        return

    selected = issues[idx]
    print("\nSelected issue:")
    print(f"#{selected['number']}  {selected['title']}")

    prompt = build_devin_prompt(selected, repo)
    session_id = create_devin_session(prompt)
    session_url = devin_ui_url(session_id)
    print(f"Devin session created: {session_id}")
    print(f"Session URL: {session_url}")

    status, data = poll_devin_session(session_id)
    print("Full data:", json.dumps(data, indent=2))
    _print_devin_output(data)
    print(f"Final status: {status}")

    while status == "blocked":
        choice = input(
            "\nNext action: (A) Approve, (R) Revise, (Q) Ask clarifying questions, (D) Deny: "
        ).strip().lower()

        if choice == "a":
            print("Approved.")
            return
        if choice == "d":
            print("Denied.")
            return
        if choice == "r":
            feedback = input("Enter revision feedback: ").strip()
            if not feedback:
                print("No feedback provided, skipping.")
                continue
            revision_message = (
                "TASK:\n"
                "Revise the previously proposed engineering plan based on the user feedback below.\n\n"
                "USER FEEDBACK:\n"
                f"{feedback}\n\n"
                "CONSTRAINTS:\n"
                "- Planning only, no repo access.\n"
                "- Do not invent repo-specific facts.\n\n"
                "OUTPUT FORMAT (strict):\n"
                "Return JSON only with keys:\n"
                "- summary\n"
                "- plan_steps\n"
                "- risks\n"
                "- confidence\n"
            )
            send_devin_message(session_id, revision_message)
            status, data = poll_devin_session(session_id)
            _print_devin_output(data)
            print(f"Status: {status}")
            continue
        if choice == "q":
            clarify_prompt = (
                "Return JSON only, no markdown fences, with keys: "
                "questions (array of 5-10 short questions to unblock a better plan), "
                "why_needed (array same length explaining why each question matters), "
                "confidence (0-1)."
            )
            send_devin_message(session_id, clarify_prompt)
            status, data = poll_devin_session(session_id)
            _print_devin_output(data)
            print(f"Status: {status}")
            continue

        print("Invalid choice. Please enter A, R, Q, or D.")

def list_issues(repo: str, limit: int = 10):
    owner, name = repo.split("/", 1)

    token = os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{owner}/{name}/issues"

    issues = []
    page = 1
    per_page = 100  # max GitHub allows

    while len(issues) < limit:
        params = {
            "state": "open",
            "per_page": per_page,
            "page": page,
        }

        r = requests.get(url, headers=headers, params=params, timeout=30)
        if r.status_code != 200:
            print("GitHub error:", r.status_code)
            print(r.text)
            return

        items = r.json()
        if not items:
            break  # no more pages

        for it in items:
            if "pull_request" in it:
                continue
            issues.append(it)
            if len(issues) >= limit:
                break

        page += 1

    if not issues:
        print("No open issues found.")
        return
    print("\nIndex | GitHub # | Title")
    print("------+----------+---------------------------")

    for i, it in enumerate(issues, start=1):
        print(f"{i:^5} | {it['number']:^8} | {it['title']}")

    return issues


def devin_ui_url(session_id: str) -> str:
    sid = session_id
    if sid.startswith("devin-"):
        sid = sid[len("devin-"):]
    return f"https://app.devin.ai/sessions/{sid}"


def build_devin_prompt(issue: dict, repo: str) -> str:
    labels = issue.get("labels") or []
    if isinstance(labels, list):
        label_names = [l.get("name", "").strip() for l in labels if l.get("name")]
        labels_str = ", ".join(label_names) if label_names else "none"
    else:
        labels_str = str(labels)

    assignees = issue.get("assignees") or []
    if isinstance(assignees, list):
        assignee_names = [a.get("login", "").strip() for a in assignees if a.get("login")]
        assignees_str = ", ".join(assignee_names) if assignee_names else "none"
    else:
        assignees_str = str(assignees)

    body_raw = issue.get("body") or ""

    prompt = (
        "TASK:\n"
        "Create a scoped engineering plan for the selected GitHub issue.\n\n"
        "IMPORTANT CONSTRAINTS:\n"
        "- Planning only. Do not implement changes.\n"
        "- Assume you do NOT have repository access. Do not clone, browse files, or reference exact file paths/line numbers unless provided in the issue text.\n"
        "- If the issue text is insufficient, ask for the minimum missing info as investigation steps.\n\n"
        "OUTPUT FORMAT (strict):\n"
        "Return JSON only (no markdown, no ``` fences, no extra text) with keys:\n"
        "- summary: string (1-3 sentences)\n"
        "- plan_steps: array of strings (5-12 items, concrete, written as actions)\n"
        "- risks: array of strings (2-8 items)\n"
        "- confidence: number between 0 and 1\n\n"
        "CONTEXT:\n"
        f"- repo: {repo}\n"
        f"- issue_number: {issue.get('number')}\n"
        f"- issue_url: {issue.get('html_url')}\n"
        f"- title: {issue.get('title')}\n"
        f"- body: {body_raw}\n"
        f"- labels: {labels_str}\n"
        f"- assignees: {assignees_str}\n\n"
        "GUIDANCE:\n"
        "- Do not invent repo-specific facts.\n"
        "- Prefer short actionable steps, include how to validate with tests/logs.\n"
        "- If you mention code locations, describe them generically (e.g., 'the cookie merge logic in Session.prepare_request').\n"
    )


    return prompt


def _get_devin_headers():
    api_key = os.getenv("DEVIN_API_KEY")
    if not api_key:
        print("DEVIN_API_KEY is missing. Please set it in your environment.")
        sys.exit(1)
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def create_devin_session(prompt: str):
    url = f"{API_BASE}/sessions"
    headers = _get_devin_headers()
    resp = requests.post(url, headers=headers, json={"prompt": prompt}, timeout=60)
    if resp.status_code < 200 or resp.status_code >= 300:
        print("Devin session creation failed:", resp.status_code)
        print(resp.text)
        sys.exit(1)
    data = resp.json()
    session_id = data.get("session_id") or data.get("id")
    if not session_id:
        print("Devin response missing session_id.")
        print(data)
        sys.exit(1)
    return session_id


def send_devin_message(session_id: str, message: str):
    url = f"{API_BASE}/sessions/{session_id}/message"
    headers = _get_devin_headers()
    resp = requests.post(url, headers=headers, json={"message": message}, timeout=60)
    if resp.status_code < 200 or resp.status_code >= 300:
        print("Failed to send message to Devin:", resp.status_code)
        print(resp.text)
        sys.exit(1)
    return resp.json()


def poll_devin_session(session_id: str, max_wait: int = 180):
    api_url = f"{API_BASE}/sessions/{session_id}"
    headers = _get_devin_headers()

    start = time.time()
    backoff = 1  # exponential backoff like the docs example

    while True:
        resp = requests.get(api_url, headers=headers, timeout=60)
        if resp.status_code < 200 or resp.status_code >= 300:
            print("Devin session poll failed:", resp.status_code)
            print(resp.text)
            sys.exit(1)

        data = resp.json()
        status = data.get("status_enum")  # use ONLY status_enum

        if status in {"finished", "blocked"}:
            # Final fetch to avoid returning a partial snapshot
            final_resp = requests.get(api_url, headers=headers, timeout=60)
            if final_resp.status_code < 200 or final_resp.status_code >= 300:
                print("Devin final fetch failed:", final_resp.status_code)
                print(final_resp.text)
                sys.exit(1)

            final_data = final_resp.json()
            final_status = final_data.get("status_enum") or status
            return final_status, final_data

        if time.time() - start > max_wait:
            print("Polling timed out. You can check the session here:")
            # Often the UI url is only returned on session creation, so this may be missing here.
            print(data.get("url") or api_url)
            return "timeout", data

        time.sleep(min(backoff, 30))
        backoff *= 2


def _print_devin_output(data: dict):
    if data.get("structured_output"):
        print("\nStructured output:")
        print(json.dumps(data["structured_output"], indent=2))
        return

    fallback = (
        data.get("output_text")
        or data.get("completion_text")
        or data.get("output")
        or data.get("response")
    )
    if fallback:
        print("\nOutput:")
        print(fallback)
        return

    messages = data.get("messages") or []
    if messages:
        last = messages[-1]
        if isinstance(last, dict):
            last_text = last.get("content") or last.get("message") or json.dumps(last, indent=2)
        else:
            last_text = str(last)
        print("\nLatest Devin message:")
        print(last_text)
        return

    print("\nNo output returned.")

def run_devin_plan(prompt: str, max_wait: int = 180):
    headers = _get_devin_headers()

    # 1) Create session
    resp = requests.post(
        f"{API_BASE}/sessions",
        headers=headers,
        json={"prompt": prompt},
        timeout=60,
    )
    if resp.status_code < 200 or resp.status_code >= 300:
        print("Failed to create Devin session:", resp.status_code)
        print(resp.text)
        sys.exit(1)

    session_data = resp.json()
    session_id = session_data["session_id"]
    session_url = session_data.get("url")

    print(f"Created session {session_id}")
    if session_url:
        print(f"URL: {session_url}")

    # 2) Poll with exponential backoff
    backoff = 1
    start = time.time()
    print("Polling for results...")

    while True:
        resp = requests.get(
            f"{API_BASE}/sessions/{session_id}",
            headers=headers,
            timeout=60,
        )
        if resp.status_code < 200 or resp.status_code >= 300:
            print("Devin session poll failed:", resp.status_code)
            print(resp.text)
            sys.exit(1)

        data = resp.json()
        status = data.get("status_enum")

        if status in {"blocked", "finished"}:
            return status, data.get("structured_output"), data

        if time.time() - start > max_wait:
            print("Polling timed out.")
            if session_url:
                print(f"Check session at: {session_url}")
            return "timeout", None, data

        time.sleep(min(backoff, 30))
        backoff *= 2


if __name__ == "__main__":
    main()


# def test_devin():
#     load_dotenv()
#     api_key = os.getenv("DEVIN_API_KEY")

#     assert api_key, "DEVIN_API_KEY not found"

#     resp = requests.post(
#         "https://api.devin.ai/v1/sessions",
#         headers={
#             "Authorization": f"Bearer {api_key}",
#             "Content-Type": "application/json",
#         },
#         json={
#             "prompt": "Say hello in one sentence and stop."
#         },
#         timeout=60,
#     )

#     print("Status:", resp.status_code)
#     print("Response:")
#     print(resp.json())
