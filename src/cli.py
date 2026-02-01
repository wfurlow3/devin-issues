import argparse
import json
import re
import sys
from dotenv import load_dotenv

from comment_selection import select_relevant_comments
from devin_client import create_devin_session, devin_ui_url, poll_devin_session, send_devin_message
from formatting import _format_structured_output, _print_devin_output
from github_client import fetch_issue_comments, list_issues
from prompt_builder import (
    build_clarify_prompt,
    build_devin_prompt,
    build_execution_prompt,
    build_pr_execution_prompt,
    build_plan_prompt,
    is_valid_clarify,
    is_valid_plan,
)
from pathlib import Path


def main(argv=None):
    load_dotenv()
    args = _parse_args(argv)
    if args.mode:
        _run_mode(args)
        return

    repo = input("Repo (owner/name): ").strip()
    if not repo:
        print("Repo is required.")
        return
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

    comments = fetch_issue_comments(repo, selected.get("number"))
    selected_comments = select_relevant_comments(comments, max_count=3)
    if comments is not None:
        print(f"Fetched {len(comments)} comments, selected {len(selected_comments)}")
        _save_issue_and_context(repo, selected, selected_comments)

    _run_plan_flow(repo, selected, selected_comments)


def _run_mode(args):
    if not args.repo or args.issue is None:
        print("Both --repo and --issue are required when --mode is set.")
        sys.exit(1)

    repo = args.repo
    issue_number = args.issue
    if args.mode == "execute":
        _run_execute_mode(repo, issue_number)
        return
    if args.mode == "execute-pr":
        _run_execute_pr_mode(repo, issue_number)
        return

    _run_plan_mode(repo, issue_number, args.fresh)


def _run_plan_mode(repo: str, issue_number: int, fresh: bool):
    base_dir = _workspace_dir(repo, issue_number)
    issue_path = base_dir / "issue.json"
    context_path = base_dir / "context.json"
    plan_path = base_dir / "plan.md"

    selected = None
    selected_comments = []
    if not fresh and issue_path.exists() and context_path.exists():
        selected = _load_json(issue_path)
        context_data = _load_json(context_path)
        selected_comments = context_data.get("comments") or []
        if plan_path.exists():
            plan_text = plan_path.read_text(encoding="utf-8")
            print("\nCurrent plan:\n")
            print(plan_text)
            data = {"output_text": plan_text}
            session_id = _load_session_id(repo, issue_number)
            _run_menu(repo, selected, selected_comments, session_id, data, status="blocked")
            return

    if selected is None:
        issues = list_issues(repo)
        if not issues:
            return
        match = None
        for it in issues:
            if it.get("number") == issue_number:
                match = it
                break
        if match is None:
            print("Issue not found in list.")
            return
        selected = match

    comments = fetch_issue_comments(repo, selected.get("number"))
    selected_comments = select_relevant_comments(comments, max_count=3)
    if comments is not None:
        print(f"Fetched {len(comments)} comments, selected {len(selected_comments)}")
        _save_issue_and_context(repo, selected, selected_comments)

    _run_plan_flow(repo, selected, selected_comments)


def _run_execute_mode(repo: str, issue_number: int):
    base_dir = _workspace_dir(repo, issue_number)
    plan_path = base_dir / "plan.md"
    if not plan_path.exists():
        print("No saved plan found. Run with --mode plan first.")
        sys.exit(1)

    plan_text = plan_path.read_text(encoding="utf-8")
    issue = {}
    context_comments = []
    issue_path = base_dir / "issue.json"
    context_path = base_dir / "context.json"
    if issue_path.exists():
        issue = _load_json(issue_path)
    if context_path.exists():
        context_data = _load_json(context_path)
        context_comments = context_data.get("comments") or []

    exec_prompt = build_execution_prompt(issue, repo, context_comments, plan_text)
    print("Starting execution session...")
    exec_session_id = create_devin_session(exec_prompt)
    exec_status, exec_data = poll_devin_session(exec_session_id, max_wait=600)
    exec_output = _extract_final_text(exec_data)
    if "REPO_ACCESS: FAILED" in exec_output:
        print("Repo access failed. Execution aborted.")
        print(exec_output)
        return
    patch_path = _write_patch_file(repo, issue_number, exec_output)
    print(f"Saved patch: {patch_path}")
    print("Inspect: git apply --stat devin.patch")
    print("Apply: git apply devin.patch")


def _run_execute_pr_mode(repo: str, issue_number: int):
    base_dir = _workspace_dir(repo, issue_number)
    plan_path = base_dir / "plan.md"
    if not plan_path.exists():
        print("No saved plan found. Run plan mode first.")
        sys.exit(1)

    plan_text = plan_path.read_text(encoding="utf-8")
    issue = {}
    context = {}
    issue_path = base_dir / "issue.json"
    context_path = base_dir / "context.json"
    if issue_path.exists():
        issue = _load_json(issue_path)
    if context_path.exists():
        context = _load_json(context_path)

    _run_execute_pr_flow(repo, issue_number, issue, context, plan_text)


def _run_plan_flow(repo: str, selected: dict, selected_comments: list):
    prompt = build_devin_prompt(selected, repo, selected_comments)
    session_id = create_devin_session(prompt)
    session_url = devin_ui_url(session_id)
    print(f"Devin session created: {session_id}")
    print(f"Session URL: {session_url}")
    _save_session(repo, selected.get("number"), session_id)

    status, data = poll_devin_session(session_id, validator=is_valid_plan, required_status={"finished", "blocked"})
    _print_devin_output(data)
    _save_plan(repo, selected.get("number"), data)
    print(f"Final status: {status}")

    _run_menu(repo, selected, selected_comments, session_id, data, status)


def _run_menu(repo: str, selected: dict, selected_comments: list, session_id, data: dict, status: str):
    while status == "blocked":
        choice = input(
            "\nNext action: (A) Approve, (R) Revise, (Q) Ask clarifying questions, (D) Deny: "
        ).strip().lower()

        if choice == "a":
            print("Approved.")
            next_action = input("Next action: (E) Execute, (P) PR, (X) Exit: ").strip().lower()
            if next_action == "x":
                return
            if next_action == "e":
                approved_plan = _extract_plan_text(data)
                exec_prompt = build_execution_prompt(selected, repo, selected_comments, approved_plan)
                print("Starting execution session...")
                exec_session_id = create_devin_session(exec_prompt)
                exec_status, exec_data = poll_devin_session(exec_session_id, max_wait=600)
                exec_output = _extract_final_text(exec_data)
                if "REPO_ACCESS: FAILED" in exec_output:
                    print("Repo access failed. Execution aborted.")
                    print(exec_output)
                    return
                patch_path = _write_patch_file(repo, selected.get("number"), exec_output)
                print(f"Saved patch: {patch_path}")
                print("Inspect: git apply --stat devin.patch")
                print("Apply: git apply devin.patch")
                return
            if next_action == "p":
                approved_plan = _extract_plan_text(data)
                context = {"comments": selected_comments}
                _run_execute_pr_flow(repo, selected.get("number"), selected, context, approved_plan)
                return
            print("Invalid choice. Please enter E, P, or X.")
            continue
        if choice == "d":
            print("Denied.")
            _delete_plan(repo, selected.get("number"))
            return
        if choice == "r":
            if session_id is None:
                print("No active planning session. Run with --fresh to regenerate.")
                continue
            feedback = input("Enter revision feedback: ").strip()
            if not feedback:
                print("No feedback provided, skipping.")
                continue
            revision_message = build_plan_prompt(selected, repo, feedback=feedback)
            send_devin_message(session_id, revision_message)
            status, data = poll_devin_session(session_id, validator=is_valid_plan, required_status={"blocked", "finished"})
            _print_devin_output(data)
            _save_plan(repo, selected.get("number"), data)
            print(f"Status: {status}")
            continue
        if choice == "q":
            if session_id is None:
                print("No active planning session. Run with --fresh to regenerate.")
                continue
            clarify_prompt = build_clarify_prompt()
            send_devin_message(session_id, clarify_prompt)
            status, data = poll_devin_session(session_id, validator=is_valid_clarify, required_status={"blocked", "finished"})
            _print_devin_output(data)
            _save_clarifying_questions(repo, selected.get("number"), data)
            print(f"Status: {status}")
            continue

        print("Invalid choice. Please enter A, R, Q, or D.")


def _parse_args(argv):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--repo", help="owner/repo")
    parser.add_argument("--issue", type=int, help="issue number")
    parser.add_argument("--mode", choices=["plan", "execute", "execute-pr"])
    parser.add_argument("--fresh", action="store_true")
    return parser.parse_args(argv)


def _extract_plan_text(data: dict) -> str:
    so = data.get("structured_output")
    formatted = _format_structured_output(so)
    if formatted:
        return formatted.strip()
    return _extract_final_text(data)


def _extract_final_text(data: dict) -> str:
    fallback = (
        data.get("output_text")
        or data.get("completion_text")
        or data.get("output")
        or data.get("response")
    )
    if fallback:
        return str(fallback)
    messages = data.get("messages") or []
    if messages:
        last = messages[-1]
        if isinstance(last, dict):
            return str(last.get("content") or last.get("message") or json.dumps(last, indent=2))
        return str(last)
    return ""


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_patch_file(repo: str, issue_number: int | None, diff_text: str) -> Path:
    root = Path(__file__).resolve().parent.parent
    repo_slug = repo.replace("/", "_")
    issue_part = f"issue-{issue_number}" if issue_number is not None else "issue-unknown"
    patch_dir = root / ".devin-workspace" / repo_slug / issue_part
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_path = patch_dir / "devin.patch"
    patch_path.write_text(diff_text)
    return patch_path


def _run_execute_pr_flow(repo: str, issue_number: int | None, issue: dict, context: dict, plan_text: str):
    exec_prompt = build_pr_execution_prompt(issue, repo, context, plan_text)
    print("Starting execution session...")
    exec_session_id = create_devin_session(exec_prompt)
    exec_status, exec_data = poll_devin_session(exec_session_id, max_wait=3600)
    exec_output = _extract_final_text(exec_data)
    pr_url = _extract_pr_url(exec_output)
    _write_pr_outputs(repo, issue_number, exec_output, pr_url)
    if pr_url:
        print(f"PR URL: {pr_url}")
    else:
        reason = _extract_pr_failure_reason(exec_output)
        print("PR creation failed.")
        print(f"Reason: {reason}")
        choice = input("Would you like to generate a patch instead using the existing plan? [y/N] ").strip().lower()
        if choice == "y":
            _run_execute_patch_from_plan(repo, issue_number, issue, context, plan_text)
        return


def _extract_pr_url(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r"https?://\S+/pull/\d+", text)
    if match:
        return match.group(0)
    return None


def _extract_pr_failure_reason(text: str) -> str:
    if not text:
        return "unknown reason"
    for line in text.splitlines():
        if line.strip().lower().startswith("reason:"):
            return line.split(":", 1)[1].strip() or "unknown reason"
    return "unknown reason"


def _run_execute_patch_from_plan(repo: str, issue_number: int | None, issue: dict, context: dict, plan_text: str):
    comments = context.get("comments") if isinstance(context, dict) else []
    exec_prompt = build_execution_prompt(issue, repo, comments, plan_text)
    print("Starting execution session...")
    exec_session_id = create_devin_session(exec_prompt)
    exec_status, exec_data = poll_devin_session(exec_session_id, max_wait=600)
    exec_output = _extract_final_text(exec_data)
    if "REPO_ACCESS: FAILED" in exec_output:
        print("Repo access failed. Execution aborted.")
        print(exec_output)
        return
    patch_path = _write_patch_file(repo, issue_number, exec_output)
    print(f"Saved patch: {patch_path}")
    print("Inspect: git apply --stat devin.patch")
    print("Apply: git apply devin.patch")


def _write_pr_outputs(repo: str, issue_number: int | None, final_text: str, pr_url: str | None):
    base_dir = _workspace_dir(repo, issue_number)
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "devin_final.md").write_text(final_text, encoding="utf-8")
    if pr_url:
        (base_dir / "pr.txt").write_text(pr_url, encoding="utf-8")


def _workspace_dir(repo: str, issue_number: int | None) -> Path:
    root = Path(__file__).resolve().parent.parent
    repo_slug = repo.replace("/", "_")
    issue_part = f"issue-{issue_number}" if issue_number is not None else "issue-unknown"
    return root / ".devin-workspace" / repo_slug / issue_part


def _save_issue_and_context(repo: str, issue: dict, comments: list | None):
    base_dir = _workspace_dir(repo, issue.get("number"))
    base_dir.mkdir(parents=True, exist_ok=True)
    issue_data = {
        "title": issue.get("title"),
        "body": issue.get("body"),
        "number": issue.get("number"),
        "url": issue.get("html_url"),
    }
    (base_dir / "issue.json").write_text(json.dumps(issue_data, indent=2), encoding="utf-8")
    context_data = {
        "comments": comments or [],
    }
    (base_dir / "context.json").write_text(json.dumps(context_data, indent=2), encoding="utf-8")


def _save_plan(repo: str, issue_number: int | None, data: dict):
    base_dir = _workspace_dir(repo, issue_number)
    base_dir.mkdir(parents=True, exist_ok=True)
    plan_text = _extract_plan_text(data)
    (base_dir / "plan.md").write_text(plan_text, encoding="utf-8")


def _save_clarifying_questions(repo: str, issue_number: int | None, data: dict):
    base_dir = _workspace_dir(repo, issue_number)
    base_dir.mkdir(parents=True, exist_ok=True)
    so = data.get("structured_output") or {}
    clarify = so.get("clarify") or {}
    questions = clarify.get("questions")
    if isinstance(questions, list) and questions:
        text = "\n".join([f"- {q}" for q in questions])
    else:
        text = _extract_final_text(data)
    (base_dir / "clarifying_questions.md").write_text(text, encoding="utf-8")


def _delete_plan(repo: str, issue_number: int | None):
    base_dir = _workspace_dir(repo, issue_number)
    plan_path = base_dir / "plan.md"
    if plan_path.exists():
        plan_path.unlink()


def _save_session(repo: str, issue_number: int | None, session_id: str):
    base_dir = _workspace_dir(repo, issue_number)
    base_dir.mkdir(parents=True, exist_ok=True)
    payload = {"session_id": session_id}
    (base_dir / "session.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_session_id(repo: str, issue_number: int | None) -> str | None:
    base_dir = _workspace_dir(repo, issue_number)
    path = base_dir / "session.json"
    if not path.exists():
        return None
    try:
        data = _load_json(path)
        return data.get("session_id")
    except Exception:
        return None
