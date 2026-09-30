#!/usr/bin/env python3
"""GitHub reuse workflow. Python 3.10+, standard library, read-only remote access."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

VERSION = "1.0.0"
API = "https://api.github.com"
SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
HOSTS = {"api.github.com", "github.com", "codeload.github.com", "raw.githubusercontent.com"}
LICENSE_NAME = re.compile(r"^(licen[cs]e|copying|notice|copyright)([._-].*)?$", re.I)
MANIFESTS = {"pyproject.toml", "package.json", "Cargo.toml", "go.mod", "requirements.txt",
             "setup.cfg", "setup.py", "manifest.json", "Dockerfile"}
LIMIT_FILE = 1024 * 1024
LIMIT_API = 16 * 1024 * 1024
LIMIT_ARCHIVE = 100 * 1024 * 1024


class ReuseError(Exception):
    """Expected actionable failure without sensitive response bodies."""


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalize_repo(value):
    if value.startswith("https://"):
        parsed = urlsplit(value)
        if parsed.netloc != "github.com" or parsed.query or parsed.fragment:
            raise ReuseError("Use an HTTPS github.com repository URL without query/fragment.")
        value = parsed.path.strip("/")
    if value.endswith(".git"):
        value = value[:-4]
    if not REPO.fullmatch(value) or any(p in {".", ".."} for p in value.split("/")):
        raise ReuseError("Repository must be owner/name or https://github.com/owner/name.")
    return value


def safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ReuseError("Unsafe repository/archive path.")
    path = PurePosixPath(value)
    raw_parts = value.rstrip("/").split("/")
    if path.is_absolute() or any(p.casefold() in {"", ".", "..", ".git"} for p in raw_parts):
        raise ReuseError("Unsafe repository/archive path.")
    for part in raw_parts:
        if any(ord(c) < 32 or c in '<>"|?*' for c in part) or part.endswith((" ", ".")):
            raise ReuseError("Non-portable repository/archive path.")
        if part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL",
                *("COM" + str(i) for i in range(1, 10)), *("LPT" + str(i) for i in range(1, 10))}:
            raise ReuseError("Reserved Windows filename.")
    return path


def read_json(path):
    try:
        result = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ReuseError(f"Cannot read JSON: {path}") from exc
    if not isinstance(result, dict):
        raise ReuseError("Expected a JSON object.")
    return result


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def new_directory(path):
    path = Path(path).expanduser().absolute()
    if path.exists() or path.is_symlink():
        raise ReuseError(f"Destination already exists; choose a new directory: {path}")
    path.mkdir(parents=True, exist_ok=False)
    return path.resolve()


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.port not in (None, 443):
            raise ReuseError("Refused redirect outside approved GitHub HTTPS hosts.")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if parsed.hostname != "api.github.com":
            redirected.remove_header("Authorization")
        return redirected


class GitHub:
    def __init__(self, token=None, timeout=30):
        self.token = token
        self.timeout = timeout
        self.opener = build_opener(SafeRedirect())

    def open(self, url):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.port not in (None, 443):
            raise ReuseError("Only approved GitHub HTTPS hosts are supported.")
        headers = {"User-Agent": "github-reuse-first/" + VERSION,
                   "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token and parsed.hostname == "api.github.com":
            headers["Authorization"] = "Bearer " + self.token
        try:
            return self.opener.open(Request(url, headers=headers), timeout=self.timeout)
        except HTTPError as exc:
            retry = exc.headers.get("Retry-After")
            reset = exc.headers.get("X-RateLimit-Reset")
            hint = f" Retry-After={retry}; rate-reset={reset}." if retry or reset else ""
            exc.close()
            raise ReuseError(f"GitHub HTTP {exc.code}; check access/rate limits.{hint}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ReuseError("GitHub network request failed; no conclusion about repository existence.") from exc

    def get(self, path, params=None):
        url = API + path
        if params:
            url += "?" + urlencode(params)
        with self.open(url) as response:
            data = response.read(LIMIT_API + 1)
        if len(data) > LIMIT_API:
            raise ReuseError("GitHub response exceeds the 16 MiB limit.")
        try:
            return json.loads(data)
        except ValueError as exc:
            raise ReuseError("GitHub returned invalid JSON.") from exc

    def file(self, repo, path, commit):
        safe_path(path)
        item = self.get(f"/repos/{repo}/contents/{quote(path, safe='/')}", {"ref": commit})
        if not isinstance(item, dict) or item.get("type") != "file":
            raise ReuseError("Requested evidence is not a regular repository file.")
        if item.get("size", 0) > LIMIT_FILE or item.get("encoding") != "base64":
            raise ReuseError("Evidence file exceeds 1 MiB or is not available as base64.")
        try:
            data = base64.b64decode(item["content"], validate=False)
        except (KeyError, ValueError) as exc:
            raise ReuseError("Invalid file content response.") from exc
        if len(data) > LIMIT_FILE:
            raise ReuseError("Evidence file exceeds 1 MiB.")
        return data

    def archive(self, repo, commit, target):
        url = f"{API}/repos/{repo}/zipball/{commit}"
        size = 0
        checksum = hashlib.sha256()
        with self.open(url) as response, Path(target).open("xb") as stream:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > LIMIT_ARCHIVE:
                    raise ReuseError("Source archive exceeds 100 MiB; use Git instead.")
                checksum.update(chunk)
                stream.write(chunk)
        return checksum.hexdigest()


def cell(value):
    return str(value if value is not None else "未知").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


