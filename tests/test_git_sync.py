import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from src.database.models.git_source_entity import GitSourceEntity
from src.models.yaml_config import parse_config
from src.services import git_sync_service as git_sync
from src.services.git import git_client
from src.services.git.git_client import TagVersion
from src.services.git.git_package_config import (SyncConfigError,
                                                 prepare_config)
from src.utils import config

# ---------------------------------------------------------------- versions


def test_version_of_strips_prefix_and_requires_semver():
    assert git_client.version_of("v1.2.3", "v") == "1.2.3"
    assert git_client.version_of("hello_world/v2.0.0", "hello_world/v") == "2.0.0"
    assert git_client.version_of("1.2.3", "") == "1.2.3"
    assert git_client.version_of("v1.2", "v") == "1.2"
    assert git_client.version_of("v1.2.3-rc.1", "v") == "1.2.3-rc.1"
    assert git_client.version_of("release-1", "v") is None
    assert git_client.version_of("vnext", "v") is None
    assert git_client.version_of("other/v1.0.0", "hello_world/v") is None
    assert git_client.version_of(None, "v") is None


def test_parse_versions_sorts_newest_first_and_ignores_other_tags():
    tags = {"v1.2.0": "a", "v1.10.0": "b", "v1.9.9": "c", "v2.0.0-rc.1": "d", "nightly": "e", "v1.10.0-beta": "f"}
    versions = git_client.parse_versions(tags, "v")
    assert [v.tag for v in versions] == ["v2.0.0-rc.1", "v1.10.0", "v1.10.0-beta", "v1.9.9", "v1.2.0"]
    assert versions[1] == TagVersion(tag="v1.10.0", version="1.10.0", commit="b")


def test_is_newer():
    assert git_client.is_newer("1.0.0", None)
    assert git_client.is_newer("1.10.0", "1.9.0")
    assert not git_client.is_newer("1.0.0", "1.0.0")
    assert not git_client.is_newer("1.0.0", "1.0.1")


# ---------------------------------------------------------------- validation

def test_normalize_path():
    assert git_client.normalize_path("") == ""
    assert git_client.normalize_path(None) == ""
    assert git_client.normalize_path("/apps//hello/") == "apps/hello"
    assert git_client.normalize_path("apps\\hello") == "apps/hello"
    assert git_client.normalize_path("./apps") == "apps"
    with pytest.raises(ValueError):
        git_client.normalize_path("apps/../../etc")
    with pytest.raises(ValueError):
        git_client.normalize_path("--upload-pack=evil")


def test_validate_repo_url(monkeypatch):
    monkeypatch.setattr(config, "GIT_ALLOW_FILE_URLS", False)
    assert git_client.validate_repo_url(" https://dev.azure.com/org/project/_git/repo ") == \
        "https://dev.azure.com/org/project/_git/repo"
    for url in ["git@github.com:org/repo.git", "ext::sh -c touch% /tmp/pwned", "--upload-pack=x",
                "file:///tmp/repo.git", "https://user:secret@github.com/org/repo.git"]:
        with pytest.raises(ValueError):
            git_client.validate_repo_url(url)

    monkeypatch.setattr(config, "GIT_ALLOW_FILE_URLS", True)
    assert git_client.validate_repo_url("file:///tmp/repo.git") == "file:///tmp/repo.git"


def test_same_origin_protects_stored_tokens():
    assert git_client.same_origin("https://dev.azure.com/org/a/_git/x", "https://DEV.azure.com/org/b/_git/y")
    assert not git_client.same_origin("https://github.com/org/repo", "https://evil.example.com/org/repo")
    assert not git_client.same_origin("https://github.com/org/repo", "http://github.com/org/repo")
    assert not git_client.same_origin("https://github.com/org/repo", "https://github.com.evil.example/org/repo")


# ---------------------------------------------------------------- config.yaml

REPO_CONFIG = """
package_name: hello_world
version: 0.0.0-ignored
runtime: python
entrypoint: main.py
python_version: 3.12.0
environment:
  - name: AGE
    value: "32"
  - name: DB_PASSWORD
    secret: true
  - name: API_KEY
"""

PREVIOUS_CONFIG = """
package_name: hello_world
version: 1.0.0
python_version: 3.12.0
entrypoint: main.py
environment:
  - name: AGE
    value: "30"
  - name: DB_PASSWORD
    value: s3cr3t
    secret: true
  - name: API_KEY
    value: abc
"""


def test_prepare_config_uses_tag_version_and_inherits_empty_values():
    content = prepare_config(REPO_CONFIG, "hello_world", "1.1.0", PREVIOUS_CONFIG)
    parsed = parse_config(content)
    assert parsed.version == "1.1.0"
    assert parsed.package_name == "hello_world"
    env = {e.name: e for e in parsed.environment}
    assert env["AGE"].value == "32"  # values from Git win
    assert env["DB_PASSWORD"].value == "s3cr3t"
    assert env["DB_PASSWORD"].is_secret
    assert env["API_KEY"].value == "abc"


def test_prepare_config_without_previous_version_keeps_empty_values():
    parsed = parse_config(prepare_config(REPO_CONFIG, "hello_world", "1.0.0", None))
    assert {e.name: e.value for e in parsed.environment}["DB_PASSWORD"] == ""


def test_prepare_config_sets_missing_package_name():
    content = prepare_config("entrypoint: main.py\npython_version: 3.12.0\n", "hello_world", "1.0.0", None)
    assert yaml.safe_load(content)["package_name"] == "hello_world"


@pytest.mark.parametrize("config_text, message", [
    ("package_name: other\n", "doesn't match"),
    ("package_name: hello_world\nruntime: binary\n", "Binary"),
    ("- just\n- a list\n", "mapping"),
    ("package_name: [unclosed\n", "not valid YAML"),
    ("runtime: cobol\n", "invalid"),
])
def test_prepare_config_rejects_invalid_configs(config_text, message):
    with pytest.raises(SyncConfigError, match=message):
        prepare_config(config_text, "hello_world", "1.0.0", None)


# ---------------------------------------------------------------- status

def _source(**values) -> GitSourceEntity:
    defaults = dict(id="s1", package_name="hello_world", repo_url="https://example.com/r.git", path="",
                    tag_prefix="v", auto_sync=True, prune_previous=False, poll_interval_seconds=120,
                    webhook_token="t", created_at=datetime.now())
    defaults.update(values)
    return GitSourceEntity(**defaults)


def test_compute_status():
    now = datetime.now()
    assert git_sync.compute_status(_source(), None) == git_sync.SyncStatus.UNKNOWN
    assert git_sync.compute_status(_source(last_checked_at=now), None) == git_sync.SyncStatus.NO_TAGS
    assert git_sync.compute_status(_source(last_checked_at=now, latest_tag="v1.1.0"), "1.1.0") == \
        git_sync.SyncStatus.SYNCED
    assert git_sync.compute_status(_source(last_checked_at=now, latest_tag="v1.1.0"), "1.0.0") == \
        git_sync.SyncStatus.OUT_OF_SYNC
    assert git_sync.compute_status(_source(last_checked_at=now, latest_tag="v1.1.0", last_error="boom"),
                                   "1.1.0") == git_sync.SyncStatus.ERROR


def test_baseline_tag_is_newest_deployed_version():
    versions = git_client.parse_versions({"v1.0.0": "a", "v1.1.0": "b", "v1.2.0": "c"}, "v")
    assert git_sync.baseline_tag(versions, {"1.0.0", "1.1.0"}).tag == "v1.1.0"
    assert git_sync.baseline_tag(versions, set()) is None


# ---------------------------------------------------------------- git against a local repository

def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
                   cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def remote(tmp_path, monkeypatch) -> str:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    monkeypatch.setattr(config, "GIT_ALLOW_FILE_URLS", True)

    work = tmp_path / "work"
    (work / "apps" / "hello").mkdir(parents=True)
    (work / "apps" / "hello" / "config.yaml").write_text("package_name: hello\n")
    (work / "apps" / "hello" / "main.py").write_text("print('v1')\n")
    (work / "README.md").write_text("root\n")
    _git("init", "-q", "-b", "main", cwd=work)
    _git("add", ".", cwd=work)
    _git("commit", "-q", "-m", "v1", cwd=work)
    _git("tag", "v1.0.0", cwd=work)
    (work / "apps" / "hello" / "main.py").write_text("print('v2')\n")
    _git("commit", "-q", "-am", "v2", cwd=work)
    _git("tag", "-a", "v1.1.0", "-m", "annotated", cwd=work)
    _git("tag", "nightly", cwd=work)

    bare = tmp_path / "remote.git"
    _git("clone", "-q", "--bare", str(work), str(bare), cwd=tmp_path)
    return bare.as_uri()


def test_list_tags_resolves_annotated_tags_to_commits(remote, tmp_path):
    tags = git_client.list_tags(remote, None)
    assert set(tags) == {"v1.0.0", "v1.1.0", "nightly"}
    # the annotated tag points to the same commit as the lightweight tag created after it
    assert tags["v1.1.0"] == tags["nightly"]
    assert tags["v1.0.0"] != tags["v1.1.0"]
    assert [v.tag for v in git_client.parse_versions(tags, "v")] == ["v1.1.0", "v1.0.0"]


def test_checkout_of_a_subfolder(remote, tmp_path):
    destination = tmp_path / "checkout"
    commit = git_client.checkout(remote, None, "v1.0.0", destination, "apps/hello")
    assert commit == git_client.list_tags(remote, None)["v1.0.0"]
    assert (destination / "apps" / "hello" / "main.py").read_text() == "print('v1')\n"


def test_checkout_of_unknown_tag_fails(remote, tmp_path):
    with pytest.raises(git_client.GitError):
        git_client.checkout(remote, None, "v9.9.9", tmp_path / "checkout")


def test_checkout_pulls_submodules(remote, tmp_path):
    work = tmp_path / "parent"
    (work / "apps" / "app").mkdir(parents=True)
    (work / "apps" / "app" / "config.yaml").write_text("package_name: app\n")
    _git("init", "-q", "-b", "main", cwd=work)
    _git("-c", "protocol.file.allow=always", "submodule", "add", "-q", remote, "apps/app/lib", cwd=work)
    _git("commit", "-q", "-am", "with submodule", cwd=work)
    _git("tag", "v1.0.0", cwd=work)
    bare = tmp_path / "parent.git"
    _git("clone", "-q", "--bare", str(work), str(bare), cwd=tmp_path)

    for path in ["", "apps/app"]:
        destination = tmp_path / f"checkout-{len(path)}"
        git_client.checkout(bare.as_uri(), None, "v1.0.0", destination, path)
        assert (destination / "apps" / "app" / "lib" / "apps" / "hello" / "main.py").read_text() == "print('v2')\n"


def test_token_is_only_sent_to_the_server_of_the_repository():
    auth = git_client.GitAuth(username=None, token="supersecret")
    env = git_client._environment(auth, "https://git.example.com:8443/org/repo.git")  # pylint: disable=protected-access
    keys = [env[f"GIT_CONFIG_KEY_{i}"] for i in range(int(env["GIT_CONFIG_COUNT"]))]
    assert "http.https://git.example.com:8443.extraHeader" in keys
    assert "http.extraHeader" not in keys


def test_list_tags_of_missing_repository_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GIT_ALLOW_FILE_URLS", True)
    with pytest.raises(git_client.GitError):
        git_client.list_tags((tmp_path / "missing.git").as_uri(), None)


def test_git_never_prompts_for_credentials(monkeypatch):
    # what VS Code puts into its terminals
    monkeypatch.setenv("GIT_ASKPASS", "c:/vscode/askpass.sh")
    monkeypatch.setenv("VSCODE_GIT_ASKPASS_MAIN", "c:/vscode/askpass-main.js")
    env = git_client._environment(None)  # pylint: disable=protected-access
    assert env["GIT_ASKPASS"] == "" and env["SSH_ASKPASS"] == "" and env["GIT_TERMINAL_PROMPT"] == "0"
    assert not any(name.startswith("VSCODE_GIT_") for name in env)


def test_private_repository_without_token_fails_instead_of_prompting(tmp_path, monkeypatch):
    """A server that demands credentials: git must fail fast, not wait for a prompt."""
    import http.server  # pylint: disable=import-outside-toplevel
    import threading  # pylint: disable=import-outside-toplevel

    class AuthRequired(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="private"')
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), AuthRequired)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # an askpass that would answer if git called it
    askpass = tmp_path / ("askpass.bat" if os.name == "nt" else "askpass.sh")
    askpass.write_text("@echo someone\n" if os.name == "nt" else "#!/bin/sh\necho someone\n")
    askpass.chmod(0o755)
    monkeypatch.setenv("GIT_ASKPASS", str(askpass))
    try:
        with pytest.raises(git_client.GitError, match="(?i)terminal prompts disabled|could not read Username"):
            git_client.list_tags(f"http://127.0.0.1:{server.server_port}/private.git", None)
    finally:
        server.shutdown()


def test_token_is_sent_as_header_and_not_leaked_in_errors(monkeypatch):
    auth = git_client.GitAuth(username=None, token="supersecret")
    env = git_client._environment(auth)  # pylint: disable=protected-access
    headers = [env[f"GIT_CONFIG_VALUE_{i}"] for i in range(int(env["GIT_CONFIG_COUNT"]))]
    assert any(h.startswith("Authorization: Basic ") for h in headers)
    assert "supersecret" not in " ".join(headers)  # base64 encoded

    class Result:
        returncode = 128
        stdout = ""
        stderr = "fatal: unable to access: header Authorization: Basic Z2l0OnN1cGVyc2VjcmV0 rejected"

    monkeypatch.setattr(git_client.subprocess, "run", lambda *a, **k: Result())
    with pytest.raises(git_client.GitError) as error:
        git_client.list_tags("https://example.com/repo.git", None)
    assert "Z2l0OnN1cGVyc2VjcmV0" not in str(error.value)
