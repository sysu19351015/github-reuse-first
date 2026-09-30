"""Offline invariant and workflow tests. Never accesses real GitHub."""
import copy
import hashlib
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import reuse
import install

COMMIT = "a" * 40
TREE = "b" * 40
REPO = "example/project"
LICENSE = b"Example permission text\n"
SOURCE = b"print('not executed')\n"


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def tree_entry(path, data):
    return {"path": path, "mode": "100644", "type": "blob", "sha": blob(data), "size": len(data)}


def inspection():
    return {"schema_version": 1, "repository_url": "https://github.com/" + REPO,
            "requested_ref": "main", "resolved_commit": COMMIT, "tree_sha": TREE,
            "tree_truncated": False, "tree": [tree_entry("LICENSE", LICENSE), tree_entry("main.py", SOURCE)],
            "evidence": [{"path": "LICENSE", "sha256": reuse.digest(LICENSE), "kind": "license",
                          "url": "https://github.com/example/project/blob/" + COMMIT + "/LICENSE"}]}


def review():
    return {"schema_version": 1, "repository_url": "https://github.com/" + REPO,
            "resolved_commit": COMMIT, "status": "reviewed_for_use", "identifier": "fixture",
            "intended_use": "Offline test only", "license_files": inspection()["evidence"],
            "obligations": ["Keep original notice"], "unresolved": [], "selection_basis": "User selected fixture"}


def zip_bytes(items):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in items:
            archive.writestr(name, data)
    return stream.getvalue()


class FakeGitHub:
    def __init__(self):
        self.tree = inspection()["tree"]
        self.truncated = False
        self.archive_data = zip_bytes([("repo/LICENSE", LICENSE), ("repo/main.py", SOURCE)])
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        if path.endswith("/commits/main") or path.endswith("/commits/" + COMMIT):
            return {"sha": COMMIT, "commit": {"tree": {"sha": TREE}}}
        if "/git/trees/" in path:
            return {"tree": self.tree, "truncated": self.truncated}
        if path == "/repos/" + REPO:
            return {"full_name": REPO, "html_url": "https://github.com/" + REPO, "default_branch": "main"}
        raise AssertionError(path)

    def file(self, repo, path, commit):
        return {"LICENSE": LICENSE, "main.py": SOURCE}[path]

    def archive(self, repo, commit, target):
        Path(target).write_bytes(self.archive_data)
        return reuse.digest(self.archive_data)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ip = self.root / "inspection.json"
        self.rp = self.root / "review.json"
        reuse.write_json(self.ip, inspection())
        reuse.write_json(self.rp, review())

    def acquire(self, client=None):
        return reuse.acquire(client or FakeGitHub(), self.ip, self.rp, self.root / "source", self.root / "reports")

    def test_full_workflow_and_integrity(self):
        client = FakeGitHub()
        inspected = reuse.inspect_repo(client, REPO, "main", self.root / "evidence")
        self.assertEqual(inspected["resolved_commit"], COMMIT)
        draft = reuse.read_json(self.root / "evidence/review.json")
        self.assertEqual(draft["status"], "needs_review")
        record = self.acquire(client)
        self.assertEqual(record["status"], "complete")
        self.assertEqual(record["verification"]["source_checks"]["git_blobs_verified"], 2)
        self.assertEqual(record["verification"]["runtime_checks"]["status"], "not_run")
        self.assertEqual((self.root / "source/main.py").read_bytes(), SOURCE)
        self.assertTrue((self.root / "reports/development-plan.md").is_file())
        self.assertTrue(reuse.validate_record(record))

    def test_unreviewed_license_blocks_before_files(self):
        data = review()
        data["status"] = "needs_review"
        reuse.write_json(self.rp, data)
        with self.assertRaises(reuse.ReuseError):
            self.acquire()
        self.assertFalse((self.root / "source").exists())
        self.assertFalse((self.root / "reports").exists())

    def test_stale_review_blocks(self):
        data = review()
        data["resolved_commit"] = "c" * 40
        with self.assertRaises(reuse.ReuseError):
            reuse.validate_review(inspection(), data)

    def test_wrong_repository_blocks(self):
        data = review()
        data["repository_url"] = "https://github.com/other/repo"
        with self.assertRaises(reuse.ReuseError):
            reuse.validate_review(inspection(), data)

    def test_missing_review_evidence_blocks(self):
        data = review()
        data["license_files"] = []
        with self.assertRaises(reuse.ReuseError):
            reuse.validate_review(inspection(), data)

    def test_existing_destination_preserved(self):
        dest = self.root / "source"
        dest.mkdir()
        (dest / "user.txt").write_text("keep")
        with self.assertRaises(reuse.ReuseError):
            self.acquire()
        self.assertEqual((dest / "user.txt").read_text(), "keep")

    def test_report_cannot_be_inside_source(self):
        with self.assertRaises(reuse.ReuseError):
            reuse.acquire(FakeGitHub(), self.ip, self.rp, self.root / "src", self.root / "src/reports")

    def test_modified_archive_is_failure_and_recorded(self):
        client = FakeGitHub()
        client.archive_data = zip_bytes([("repo/LICENSE", LICENSE), ("repo/main.py", b"tampered")])
        with self.assertRaises(reuse.ReuseError):
            self.acquire(client)
        record = reuse.read_json(self.root / "reports/source-record.json")
        self.assertEqual(record["status"], "failed")
        self.assertIn("differs", record["failure_reason"])
        self.assertTrue((self.root / "source/main.py").exists())

    def test_license_hash_mismatch_is_failure(self):
        edited = inspection()
        edited["evidence"][0]["sha256"] = "0" * 64
        approved = review()
        approved["license_files"] = edited["evidence"]
        reuse.write_json(self.ip, edited)
        reuse.write_json(self.rp, approved)
        with self.assertRaises(reuse.ReuseError):
            self.acquire()
        self.assertIn("license differs", reuse.read_json(self.root / "reports/source-record.json")["failure_reason"])

    def test_missing_files_are_partial(self):
        client = FakeGitHub()
        client.archive_data = zip_bytes([("repo/LICENSE", LICENSE)])
        record = self.acquire(client)
        self.assertEqual(record["status"], "partial")
        self.assertIn("main.py", record["missing_items"])

    def test_lfs_and_submodules_are_partial(self):
        client = FakeGitHub()
        pointer = b"version https://git-lfs.github.com/spec/v1\noid sha256:123\nsize 12\n"
        client.tree += [tree_entry("asset.bin", pointer),
                        {"type": "commit", "mode": "160000", "sha": "c" * 40, "path": "vendor/lib"}]
        client.archive_data = zip_bytes([("repo/LICENSE", LICENSE), ("repo/main.py", SOURCE), ("repo/asset.bin", pointer)])
        record = self.acquire(client)
        self.assertEqual(record["status"], "partial")
        self.assertTrue(any("LFS" in x for x in record["missing_items"]))
        self.assertTrue(any("submodule" in x for x in record["missing_items"]))

    def test_truncated_tree_never_complete(self):
        client = FakeGitHub()
        client.truncated = True
        self.assertEqual(self.acquire(client)["status"], "partial")

    def test_untrusted_inspection_tree_refetched(self):
        edited = inspection()
        edited["tree"] = []
        reuse.write_json(self.ip, edited)
        self.assertEqual(self.acquire()["verification"]["source_checks"]["git_blobs_verified"], 2)

    def test_complete_record_cannot_claim_missing_files(self):
        record = self.acquire()
        record["missing_items"] = ["missing.py"]
        with self.assertRaises(reuse.ReuseError):
            reuse.validate_record(record)

    def test_record_requires_archive_digest(self):
        record = self.acquire()
        record["archive_sha256"] = None
        with self.assertRaises(reuse.ReuseError):
            reuse.validate_record(record)

    def test_invalid_record_rejected(self):
        with self.assertRaises(reuse.ReuseError):
            reuse.validate_record({"schema_version": 1, "status": "bogus"})

    def test_report_requires_evidence(self):
        data = {"goal": "Build tool", "candidates": [{"repository": REPO, "fit": "unknown",
                "gaps": "unknown", "effort": "unknown", "license_status": "needs_review", "evidence": []}]}
        path = self.root / "assessment.json"
        reuse.write_json(path, data)
        with self.assertRaises(reuse.ReuseError):
            reuse.render_report(path, self.root / "report")

    def test_report_renders_unicode_and_evidence(self):
        data = {"goal": "离线工具", "search_scope": "模拟数据", "candidates": [{"repository": REPO,
                "fit": "文档声明", "gaps": "待运行验证", "effort": "中", "license_status": "needs_review",
                "evidence": [{"claim": "支持离线", "status": "documented", "url": "https://github.com/example/project"}]}]}
        path = self.root / "assessment.json"
        reuse.write_json(path, data)
        reuse.render_report(path, self.root / "report")
        self.assertIn("documented", (self.root / "report/comparison.md").read_text(encoding="utf-8"))


class ArchiveTests(unittest.TestCase):
    def check_bad(self, items, **kwargs):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "a.zip"
            archive.write_bytes(zip_bytes(items))
            destination = Path(temp) / "out"
            with self.assertRaises(reuse.ReuseError):
                reuse.extract_archive(archive, destination, **kwargs)
            self.assertFalse(destination.exists())

    def test_traversal(self):
        self.check_bad([("root/../../escaped", b"x")])

    def test_absolute_path(self):
        self.check_bad([("/root/file", b"x")])

    def test_backslash(self):
        self.check_bad([("root/..\\escape", b"x")])

    def test_reserved_windows_name(self):
        self.check_bad([("root/CON.txt", b"x")])

    def test_git_metadata(self):
        self.check_bad([("root/.git/config", b"x")])

    def test_git_metadata_case_alias(self):
        self.check_bad([("root/.GiT/config", b"x")])

    def test_windows_alternate_filename(self):
        self.check_bad([('root/file?.txt', b"x")])

    def test_case_collision(self):
        self.check_bad([("root/a", b"a"), ("root/A", b"b")])

    def test_multiple_roots(self):
        self.check_bad([("one/a", b"a"), ("two/b", b"b")])

    def test_file_directory_collision(self):
        self.check_bad([("root/a", b"x"), ("root/a/b", b"y")])

    def test_size_limit(self):
        self.check_bad([("root/a", b"123")], max_size=2)

    def test_symlink(self):
        item = zipfile.ZipInfo("root/link")
        item.create_system = 3
        item.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.check_bad([(item, b"/outside")])


class NetworkTests(unittest.TestCase):
    def test_repository_normalization(self):
        self.assertEqual(reuse.normalize_repo("https://github.com/a/b.git"), "a/b")
        for bad in ["../bad", "https://evil.test/a/b", "https://user:secret@github.com/a/b",
                    "a/b?x", "a/b/c", "-a/b"]:
            with self.subTest(value=bad), self.assertRaises(reuse.ReuseError):
                reuse.normalize_repo(bad)

    def test_cross_host_redirect_strips_token(self):
        req = Request("https://api.github.com/repos/a/b/zipball/x",
                      headers={"Authorization": "Bearer secret"})
        redirected = reuse.SafeRedirect().redirect_request(req, None, 302, "Found", {},
                                                          "https://codeload.github.com/a/b/legacy.zip/x")
        self.assertIsNone(redirected.get_header("Authorization"))

    def test_bad_redirect_refused(self):
        req = Request("https://api.github.com/test")
        for url in ["http://github.com/a", "https://evil.test/a"]:
            with self.assertRaises(reuse.ReuseError):
                reuse.SafeRedirect().redirect_request(req, None, 302, "", {}, url)

    def test_rate_limit_does_not_retry_or_expose_body(self):
        client = reuse.GitHub("secret")
        error = HTTPError("https://api.github.com/test", 403, "denied",
                          {"Retry-After": "60"}, io.BytesIO(b"secret response"))
        with patch.object(client.opener, "open", side_effect=error) as call:
            with self.assertRaises(reuse.ReuseError) as ctx:
                client.get("/test")
            self.assertEqual(call.call_count, 1)
            self.assertIn("Retry-After=60", str(ctx.exception))
            self.assertNotIn("secret", str(ctx.exception))

    def test_search_deduplicates_and_records_pagination(self):
        class SearchClient:
            def get(self, path, params):
                name = "a/one" if params["page"] == 1 else "a/two"
                return {"total_count": 2, "incomplete_results": False,
                        "items": [{"full_name": name, "html_url": "https://github.com/" + name}]}
        with tempfile.TemporaryDirectory() as temp:
            result = reuse.search(SearchClient(), ["topic", "synonym"], Path(temp) / "out", limit=1, pages=2)
        self.assertEqual(len(result["candidates"]), 2)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["queries"][0]["pages_fetched"], 2)

    def test_search_failure_is_limited_not_no_results(self):
        class Failing:
            def get(self, *args):
                raise reuse.ReuseError("GitHub HTTP 403")
        with tempfile.TemporaryDirectory() as temp:
            result = reuse.search(Failing(), ["topic"], Path(temp) / "out")
        self.assertEqual(result["status"], "limited")
        self.assertTrue(result["errors"])


class InstallerTests(unittest.TestCase):
    def test_upgrade_preserves_backup(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "installed"
            installed, backup = install.install(source, dest)
            self.assertIsNone(backup)
            (dest / "local-note.txt").write_text("keep")
            with self.assertRaises(ValueError):
                install.install(source, dest)
            installed, backup = install.install(source, dest, upgrade=True)
            self.assertEqual((backup / "local-note.txt").read_text(), "keep")
            self.assertTrue((installed / "scripts/reuse.py").is_file())


if __name__ == "__main__":
    unittest.main()
