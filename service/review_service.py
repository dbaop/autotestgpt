"""
Code review task service — git diff 收集 + 双 Agent LLM 并行智能分析。
"""

from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _is_git_repo(path: str) -> bool:
    git_dir = Path(path) / ".git"
    return git_dir.exists()


def _resolve_repo_path(task: CodeReviewTask) -> str:
    if task.repo_type == "local":
        local_path = task.repo_path or ""
        if not local_path.strip():
            raise RuntimeError("repo_path is required for local review")
        resolved = str(Path(local_path.strip()).resolve())
        if not os.path.isdir(resolved):
            raise RuntimeError(f"Local path does not exist: {resolved}")
        if not _is_git_repo(resolved):
            raise RuntimeError(f"Path is not a git repository: {resolved}")
        return resolved

    repo_url = (task.repo_url or "").strip()
    if not repo_url:
        raise RuntimeError("repo_url is required for remote review")

    repo_name = _repo_name_from_url(repo_url)
    repos_root = Path(Config.WORKSPACE) / "repos"
    repos_root.mkdir(parents=True, exist_ok=True)
    repo_path = repos_root / repo_name

    if repo_path.exists():
        _run_git(["git", "fetch", "--all", "--prune"], cwd=str(repo_path))
    else:
        _run_git(["git", "clone", repo_url, str(repo_path)])

    return str(repo_path)


# ---------------------------------------------------------------------------
# 双 Agent 配置
# ---------------------------------------------------------------------------

def _build_review_agents():
    """构建安全审查 Agent（MiniMax）和质量审查 Agent（DeepSeek）。"""
    from agent.review_agent import ReviewAgent

    agents = []
    has_minimax = bool(getattr(Config, "MINIMAX_API_KEY", None))
    has_deepseek = bool(getattr(Config, "DEEPSEEK_API_KEY", None))

    # 按思路：MiniMax 做安全/逻辑审查，DeepSeek 做质量/性能审查
    if has_minimax and has_deepseek:
        agents.append(ReviewAgent(
            review_type="security_logic",
            force_model="minimax/abab6.5s-chat",
            api_key=Config.MINIMAX_API_KEY,
            api_base="https://api.minimax.chat/v1",
        ))
        agents.append(ReviewAgent(
            review_type="quality_perf",
            force_model="deepseek/deepseek-chat",
            api_key=Config.DEEPSEEK_API_KEY,
        ))
    elif has_deepseek:
        agents.append(ReviewAgent(
            review_type="security_logic",
            force_model="deepseek/deepseek-chat",
            api_key=Config.DEEPSEEK_API_KEY,
        ))
        agents.append(ReviewAgent(
            review_type="quality_perf",
            force_model="deepseek/deepseek-chat",
            api_key=Config.DEEPSEEK_API_KEY,
        ))
    elif has_minimax:
        agents.append(ReviewAgent(
            review_type="security_logic",
            force_model="minimax/abab6.5s-chat",
            api_key=Config.MINIMAX_API_KEY,
            api_base="https://api.minimax.chat/v1",
        ))
        agents.append(ReviewAgent(
            review_type="quality_perf",
            force_model="minimax/abab6.5s-chat",
            api_key=Config.MINIMAX_API_KEY,
            api_base="https://api.minimax.chat/v1",
        ))
    else:
        # 没有任何 LLM key，创建一个 fallback agent（走默认自动解析）
        agents.append(ReviewAgent(review_type="security_logic"))
        agents.append(ReviewAgent(review_type="quality_perf"))
    return agents


def _analyze_commit_with_agents(agents, commit_sha: str, commit_msg: str,
                                diff_text: str) -> List[dict]:
    """用双 Agent 并行分析单个 commit 的 diff。"""
    from agent.review_agent import merge_review_results

    input_data = {
        "commit_sha": commit_sha,
        "commit_msg": commit_msg,
        "diff_text": diff_text,
    }

    results = {}
    with ThreadPoolExecutor(max_workers=len(agents)) as pool:
        future_map = {
            pool.submit(agent.process, input_data): agent.review_type
            for agent in agents
        }
        for future in as_completed(future_map):
            review_type = future_map[future]
            try:
                results[review_type] = future.result()
            except Exception as exc:
                results[review_type] = {"findings": [], "summary": "", "error": str(exc)}

    return merge_review_results(
        results.get("security_logic", {}),
        results.get("quality_perf", {}),
    )


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def run_review_task(task_id: int):
    task = db.session.get(CodeReviewTask, task_id)
    if not task:
        return {"status": "error", "message": f"task {task_id} not found"}

    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    db.session.commit()

    try:
        repo_path = _resolve_repo_path(task)
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

        # 构建双 Agent
        agents = _build_review_agents()

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

            # LLM 双 Agent 并行分析
            llm_findings = _analyze_commit_with_agents(
                agents, commit_sha, subject, diff_text
            )

            if llm_findings:
                for f in llm_findings:
                    finding = CodeReviewFinding(
                        task_id=task.id,
                        commit_sha=commit_sha,
                        file_path=f.get("file_path"),
                        severity=f.get("severity", "info"),
                        category=f.get("category"),
                        review_type=f.get("review_type"),
                        suggestion=f.get("suggestion"),
                        title=f.get("title", subject[:200]),
                        detail=f.get("description", ""),
                    )
                    db.session.add(finding)
                    findings_count += 1
            else:
                # LLM 没有发现问题，存一条空的 info 记录
                finding = CodeReviewFinding(
                    task_id=task.id,
                    commit_sha=commit_sha,
                    severity="info",
                    title=subject[:200],
                    detail=f"author={author}; date={commit_date}",
                )
                db.session.add(finding)
                findings_count += 1

        task.status = "completed"
        task.finished_at = datetime.now(timezone.utc)
        task.summary = (
            f"LLM审查 {len(commit_lines)} commits ({task.days}d); "
            f"生成 {findings_count} 条 findings"
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


def _run_review_task_in_context(flask_app, task_id: int):
    with flask_app.app_context():
        try:
            run_review_task(task_id)
        finally:
            db.session.remove()


def run_review_task_async(task_id: int):
    from service.flow_service import _resolve_flask_app

    flask_app = _resolve_flask_app()
    _review_executor.submit(_run_review_task_in_context, flask_app, task_id)
    return {"status": "queued", "task_id": task_id}
