import os
import requests


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


def fetch_issue_comments(repo: str, issue_number: int | None):
    if issue_number is None:
        return []
    owner, name = repo.split("/", 1)
    token = os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{owner}/{name}/issues/{issue_number}/comments"
    params = {"per_page": 100}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    if r.status_code != 200:
        print("GitHub comments error:", r.status_code)
        print(r.text)
        return None
    return r.json()
