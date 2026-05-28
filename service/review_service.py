"""
Code review task service.
"""

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from config import Config
from models import CodeReviewFinding, CodeReviewTask, db

_review_executor = ThreadPoolExecutor(max_workers=2)


def _run_git(cmd: List[str], cwd: str | None = None) -> str:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git command failed")
    return proc.stdout.strip()


def _repo_name_from_url(repo_url: str) -> str:
    repo_name = repo_url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    return repo_name or "repo"


def _ensure_local_repo(repo_url: str) -> str:
    repo_name = _repo_name_from_url(repo_url)
    repos_root = Path(Config.WORKSPACE) / "repos"
    repos_root.mkdir(parents=True, exist_ok=True)
    repo_path = repos_root / repo_name

    if repo_path.exists():
        _run_git(["git", "fetch", "--all", "--prune"], cwd=str(repo_path))
    else:
        _run_git(["git", "clone", repo_url, str(repo_path)])

    return str(repo_path)


def run_review_task(task_id: int):
    task = db.session.get(CodeReviewTask, task_id)
    if not task:
        return {"status": "error", "message": f"task {task_id} not found"}

    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    db.session.commit()

    try:
        repo_path = _ensure_local_repo(task.repo_url)
        log_output = _run_git(
            [
                "git",
                "log",
                task.branch,
                f"--since={task.days}.days",
                "--pretty=format:%H|%an|%ad|%s",
                "--date=short",
            ],
            cwd=repo_path,
        )
        commit_lines = [line for line in log_output.splitlines() if line.strip()]

        findings_count = 0
        for line in commit_lines:
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue

            commit_sha, author, commit_date, subject = parts
            diff_text = _run_git(
                ["git", "show", commit_sha, "--stat", "--patch", "--no-color"],
                cwd=repo_path,
            )

            finding = CodeReviewFinding(
                task_id=task.id,
                commit_sha=commit_sha,
                file_path=None,
                severity="info",
                title=subject[:200],
                detail=f"author={author}; date={commit_date}\n\n{diff_text[:4000]}",
            )
            db.session.add(finding)
            findings_count += 1

        task.status = "completed"
        task.finished_at = datetime.now(timezone.utc)
        task.summary = (
            f"Reviewed {len(commit_lines)} commits in last {task.days} days; "
            f"generated {findings_count} findings"
        )
        db.session.commit()

        return {
            "status": "completed",
            "task_id": task.id,
            "commits": len(commit_lines),
            "findings": findings_count,
        }
    except Exception as e:
        db.session.rollback()
        task.status = "error"
        task.finished_at = datetime.now(timezone.utc)
        task.error_message = str(e)
        db.session.commit()
        return {"status": "error", "task_id": task.id, "message": str(e)}


def run_review_task_async(task_id: int):
    _review_executor.submit(run_review_task, task_id)
    return {"status": "queued", "task_id": task_id}
