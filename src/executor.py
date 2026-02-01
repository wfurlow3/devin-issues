import subprocess
from pathlib import Path


def prepare_workspace(repo_full_name: str, issue_number: int, ref: str | None = None) -> Path:
    workspace_root = Path(".devin-workspace").resolve()
    repo_slug = repo_full_name.replace("/", "_")
    base_dir = workspace_root / repo_slug
    repo_dir = base_dir / "repo"
    issue_dir = base_dir / f"issue-{issue_number}"

    workspace_root.mkdir(parents=True, exist_ok=True)

    repo_url = f"https://github.com/{repo_full_name}.git"

    if not repo_dir.exists():
        print("Cloning repo...")
        _run_git(["clone", repo_url, str(repo_dir)])
    else:
        print("Fetching updates...")
        _run_git(["-C", str(repo_dir), "fetch", "origin"])

    default_branch = _get_default_branch(repo_dir)
    target_branch = ref or default_branch

    _run_git(["-C", str(repo_dir), "checkout", target_branch])
    _run_git(["-C", str(repo_dir), "reset", "--hard", f"origin/{target_branch}"])

    branch_name = f"devin/issue-{issue_number}"
    if issue_dir.exists():
        _run_git(["-C", str(issue_dir), "checkout", "-B", branch_name])
        _run_git(["-C", str(issue_dir), "reset", "--hard", f"origin/{target_branch}"])
    else:
        _run_git(
            [
                "-C",
                str(repo_dir),
                "worktree",
                "add",
                "-B",
                branch_name,
                str(issue_dir),
                f"origin/{target_branch}",
            ]
        )

    print(f"Created branch {branch_name}")
    return issue_dir


def _get_default_branch(repo_dir: Path) -> str:
    try:
        result = _run_git(
            ["-C", str(repo_dir), "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True,
        )
        ref = result.stdout.strip()
        return ref.split("/")[-1]
    except RuntimeError:
        result = _run_git(
            ["-C", str(repo_dir), "remote", "show", "origin"],
            capture_output=True,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("HEAD branch:"):
                return line.split(":", 1)[1].strip()
    return "main"


def _run_git(args: list[str], capture_output: bool = False):
    cmd = ["git"] + args
    result = subprocess.run(
        cmd,
        text=True,
        capture_output=capture_output,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else "unknown error"
        raise RuntimeError(f"Git command failed ({' '.join(cmd)}): {stderr}")
    return result


if __name__ == "__main__":
    prepare_workspace("psf/requests-html", 601)
