"""
GitHub API 封装
"""

import os
import base64
from github import Github, GithubException


class GitHubClient:
    def __init__(self, owner: str, repo_name: str):
        token = os.environ["GITHUB_TOKEN"]
        self.gh = Github(token)
        self.repo = self.gh.get_repo(f"{owner}/{repo_name}")
        self.default_branch = self.repo.default_branch

    def get_file_content(self, path: str, branch: str = None) -> str:
        ref = branch or self.default_branch
        content = self.repo.get_contents(path, ref=ref)
        return base64.b64decode(content.content).decode("utf-8")

    def create_branch(self, branch: str):
        ref = self.repo.get_git_ref(f"heads/{self.default_branch}")
        try:
            self.repo.create_git_ref(f"refs/heads/{branch}", ref.object.sha)
        except GithubException:
            pass  # 分支已存在

    def update_file(self, branch: str, path: str, content: str, message: str):
        try:
            existing = self.repo.get_contents(path, ref=branch)
            self.repo.update_file(path, message, content, existing.sha, branch=branch)
        except GithubException:
            self.repo.create_file(path, message, content, branch=branch)

    def create_file(self, branch: str, path: str, content: str, message: str):
        try:
            self.repo.create_file(path, message, content, branch=branch)
        except GithubException:
            pass

    def create_pr(self, title: str, body: str, head: str) -> str:
        pr = self.repo.create_pull(
            title=title,
            body=body,
            head=head,
            base=self.default_branch,
        )
        return pr.html_url

    def get_ci_status(self, branch: str) -> str:
        commit = self.repo.get_branch(branch).commit
        statuses = list(commit.get_statuses())
        if not statuses:
            checks = list(commit.get_check_runs())
            if not checks:
                return "pending"
            conclusions = [c.conclusion for c in checks]
            if all(c == "success" for c in conclusions):
                return "success"
            if any(c in ("failure", "cancelled") for c in conclusions):
                return "failure"
            return "pending"
        state = statuses[0].state
        return state  # success / failure / pending

    def get_ci_log(self, branch: str) -> str:
        commit = self.repo.get_branch(branch).commit
        checks = list(commit.get_check_runs())
        logs = []
        for check in checks:
            if check.conclusion == "failure":
                logs.append(f"[{check.name}] {check.output.summary or ''}")
        return "\n".join(logs) or "No log available"

    def add_label(self, pr_url: str, label: str):
        pr_number = int(pr_url.split("/")[-1])
        pr = self.repo.get_pull(pr_number)
        pr.add_to_labels(label)

    def add_comment(self, pr_url: str, comment: str):
        pr_number = int(pr_url.split("/")[-1])
        pr = self.repo.get_pull(pr_number)
        pr.create_issue_comment(comment)

    def request_review(self, pr_url: str):
        """通知 reviewers（如 config 中配置了）"""
        pass

