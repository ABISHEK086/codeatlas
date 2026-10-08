import io
import zipfile

import httpx

from .config import settings

API = "https://api.github.com"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _client() -> httpx.Client:
    return httpx.Client(timeout=60, follow_redirects=True)


def exchange_code(code: str) -> str:
    with _client() as c:
        r = c.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": f"{settings.backend_url}/auth/github/callback",
            },
        )
        r.raise_for_status()
        data = r.json()
    if "access_token" not in data:
        raise ValueError(data.get("error_description", "GitHub token exchange failed"))
    return data["access_token"]


def get_user(token: str) -> dict:
    with _client() as c:
        r = c.get(f"{API}/user", headers=_headers(token))
        r.raise_for_status()
        return r.json()


def get_repo(token: str, owner: str, name: str) -> dict:
    with _client() as c:
        r = c.get(f"{API}/repos/{owner}/{name}", headers=_headers(token))
        r.raise_for_status()
        return r.json()


def download_zip(token: str, owner: str, name: str, ref: str) -> zipfile.ZipFile:
    """One request for the whole repo instead of one per file."""
    with _client() as c:
        r = c.get(f"{API}/repos/{owner}/{name}/zipball/{ref}", headers=_headers(token))
        r.raise_for_status()
        return zipfile.ZipFile(io.BytesIO(r.content))


def list_commits(token: str, owner: str, name: str, limit: int) -> list[dict]:
    with _client() as c:
        r = c.get(
            f"{API}/repos/{owner}/{name}/commits",
            headers=_headers(token),
            params={"per_page": min(limit, 100)},
        )
        r.raise_for_status()
        return r.json()[:limit]


def get_commit(token: str, owner: str, name: str, sha: str) -> dict:
    with _client() as c:
        r = c.get(f"{API}/repos/{owner}/{name}/commits/{sha}", headers=_headers(token))
        r.raise_for_status()
        return r.json()