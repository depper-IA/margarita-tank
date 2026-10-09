"""Tests for the standalone statusLine bridge scripts.

The bridge sits between Claude Code and the user's statusLine: it caches the
statusLine stdin JSON (which carries rate_limits) for the daemon, then chains
the user's original statusLine command so their status line keeps working.
It runs on every statusLine refresh, so it must never fail loudly.

There are two implementations of the same contract. Windows runs the Python
script (hooks.STATUSLINE_BRIDGE_SCRIPT, frozen into margarita-statusline.exe);
macOS and Linux run a plain /bin/sh script (hooks.STATUSLINE_BRIDGE_SH) so the
user's own statusLine never depends on a working python3. The shared tests run
against both.
"""

import json
import os
import subprocess
import sys
import time

import pytest

from clawd_tank_daemon.protocol import read_usage_from_cache
from clawd_tank_menubar import hooks

PAYLOAD = {
    "model": {"display_name": "Opus"},
    "rate_limits": {
        "five_hour": {"used_percentage": 42.0, "resets_at": 1900000000},
        "seven_day": {"used_percentage": 7.0, "resets_at": 1900500000},
    },
}

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="the sh bridge is POSIX-only")


def _original_command(original):
    """The command of a saved original statusLine, as the installer extracts it."""
    line = original.get("statusLine") if isinstance(original, dict) else None
    command = line.get("command") if isinstance(line, dict) else None
    return command if isinstance(command, str) else None


class Bridge:
    """One bridge implementation, run in a sandbox dir."""

    def __init__(self, kind, tmp_path):
        self.kind = kind
        self.clawd_dir = tmp_path / "clawd"
        self.clawd_dir.mkdir()
        if kind == "python":
            self.script = tmp_path / "statusline_bridge.py"
            self.script.write_text(hooks.STATUSLINE_BRIDGE_SCRIPT, encoding="utf-8")
            self.argv = [sys.executable, str(self.script)]
            self.self_command = f'"{sys.executable}" "{self.script}"'
        else:
            self.script = tmp_path / "statusline_bridge.sh"
            self.script.write_text(hooks.STATUSLINE_BRIDGE_SH, encoding="utf-8")
            self.argv = ["/bin/sh", str(self.script)]
            self.self_command = f"/bin/sh '{self.script}'"
        self.cache = self.clawd_dir / "statusline-cache.json"

    def save_original(self, original):
        """Save the user's statusLine the way install does for this implementation."""
        (self.clawd_dir / hooks.STATUSLINE_STATE_NAME).write_text(
            json.dumps(original), encoding="utf-8")
        command = _original_command(original)
        if self.kind == "sh" and command is not None:
            (self.clawd_dir / hooks.STATUSLINE_COMMAND_NAME).write_text(
                command, encoding="utf-8")

    def run(self, stdin, original="<unset>", env=None, timeout=30):
        if original != "<unset>":
            self.save_original(original)
        full_env = {**os.environ, "CLAWD_TANK_DIR": str(self.clawd_dir), **(env or {})}
        proc = subprocess.run(
            self.argv,
            input=stdin if isinstance(stdin, bytes) else stdin.encode(),
            capture_output=True, env=full_env, timeout=timeout,
        )
        return proc, self.cache

    __call__ = run


@pytest.fixture(params=["python", pytest.param("sh", marks=posix_only)])
def bridge(request, tmp_path):
    """A callable bridge, run(stdin, original=...), for each implementation in turn."""
    return Bridge(request.param, tmp_path)


@pytest.fixture
def sh_bridge(tmp_path):
    """The POSIX sh implementation alone, for behaviour only it has."""
    if sys.platform == "win32":
        pytest.skip("the sh bridge is POSIX-only")
    return Bridge("sh", tmp_path)


def test_writes_cache_the_daemon_can_read(bridge):
    proc, cache = bridge(json.dumps(PAYLOAD))
    assert proc.returncode == 0
    usage = read_usage_from_cache(str(cache))
    assert usage["session_pct"] == 42
    assert usage["weekly_pct"] == 7


def test_write_is_atomic_and_leaves_no_temp_files(bridge):
    proc, cache = bridge(json.dumps(PAYLOAD))
    assert proc.returncode == 0
    assert sorted(p.name for p in cache.parent.iterdir()) == ["statusline-cache.json"]


def test_overwrites_previous_cache(bridge):
    bridge(json.dumps({"rate_limits": {"five_hour": {"used_percentage": 1}}}))
    proc, cache = bridge(json.dumps(PAYLOAD))
    assert json.loads(cache.read_text())["rate_limits"]["five_hour"]["used_percentage"] == 42.0


def test_no_original_prints_nothing_and_exits_zero(bridge):
    proc, _ = bridge(json.dumps(PAYLOAD))
    assert proc.returncode == 0
    assert proc.stdout == b""


def test_chains_original_command_with_same_stdin(bridge):
    # The original reads stdin and echoes the model name: proves it got the JSON.
    original_cmd = (
        f'"{sys.executable}" -c "import json,sys; '
        f'print(\'ORIG:\' + json.load(sys.stdin)[\'model\'][\'display_name\'])"'
    )
    proc, cache = bridge(
        json.dumps(PAYLOAD),
        original={"statusLine": {"type": "command", "command": original_cmd}},
    )
    assert proc.returncode == 0
    assert proc.stdout.decode().strip() == "ORIG:Opus"
    assert cache.exists()


def test_invalid_json_does_not_write_cache_but_still_chains(bridge):
    original_cmd = f'"{sys.executable}" -c "import sys; sys.stdout.write(sys.stdin.read())"'
    proc, cache = bridge(
        "not json {",
        original={"statusLine": {"type": "command", "command": original_cmd}},
    )
    assert proc.returncode == 0
    assert proc.stdout == b"not json {"
    assert not cache.exists()


def test_non_object_json_is_not_cached(bridge):
    proc, cache = bridge("[1, 2]")
    assert proc.returncode == 0
    assert not cache.exists()


def test_empty_stdin_exits_zero(bridge):
    proc, cache = bridge("")
    assert proc.returncode == 0
    assert not cache.exists()


@pytest.mark.parametrize("original", [
    "garbage-not-a-dict",
    {"statusLine": None},
    {"statusLine": {"type": "command"}},
    {"statusLine": "just a string"},
])
def test_unusable_original_state_is_ignored(bridge, original):
    proc, cache = bridge(json.dumps(PAYLOAD), original=original)
    assert proc.returncode == 0
    assert proc.stdout == b""
    assert cache.exists()


def test_failing_original_command_still_exits_zero(bridge):
    proc, cache = bridge(
        json.dumps(PAYLOAD),
        original={"statusLine": {"type": "command", "command": "definitely-not-a-command-xyz"}},
    )
    assert proc.returncode == 0
    assert proc.stderr == b""
    assert cache.exists()


def test_unwritable_cache_dir_still_chains_and_exits_zero(bridge):
    original_cmd = f'"{sys.executable}" -c "print(\'still works\')"'
    # Point the state dir at a path whose cache cannot be created.
    (bridge.clawd_dir / "statusline-cache.json").mkdir()  # replacing a directory fails
    proc, _ = bridge(
        json.dumps(PAYLOAD),
        original={"statusLine": {"type": "command", "command": original_cmd}},
    )
    assert proc.returncode == 0
    assert proc.stdout.decode().strip() == "still works"


def test_bridge_does_not_recurse_into_itself(bridge):
    proc, _ = bridge(
        json.dumps(PAYLOAD),
        original={"statusLine": {"type": "command", "command": bridge.self_command}},
    )
    assert proc.returncode == 0
    assert proc.stdout == b""


def test_python_bridge_ignores_a_corrupt_state_file(tmp_path):
    b = Bridge("python", tmp_path)
    (b.clawd_dir / hooks.STATUSLINE_STATE_NAME).write_text("{nope")
    proc, cache = b.run(json.dumps(PAYLOAD))
    assert proc.returncode == 0
    assert cache.exists()


# --- behaviour specific to the POSIX sh bridge --------------------------------

def test_sh_bridge_is_a_plain_sh_script_with_a_shebang(sh_bridge):
    text = hooks.STATUSLINE_BRIDGE_SH
    assert text.startswith("#!/bin/sh\n")
    code = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    assert not any("python" in line.lower() for line in code)
    # dedent must have left no indentation on the first lines.
    assert text.splitlines()[1].startswith("# statusline_bridge")


def test_sh_bridge_needs_no_python(sh_bridge, tmp_path):
    """The whole point: no python3 anywhere on PATH, yet the cache is written
    and the user's own statusLine still runs."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("cat", "mkdir", "mv", "rm", "sleep", "pgrep", "printf", "echo"):
        found = subprocess.run(
            ["/bin/sh", "-c", f"command -v {tool}"], capture_output=True, text=True,
        ).stdout.strip()
        if found.startswith("/"):
            (bin_dir / tool).symlink_to(found)
    sh_bridge.save_original(
        {"statusLine": {"type": "command", "command": "echo mine; cat >/dev/null"}})
    proc, cache = sh_bridge.run(json.dumps(PAYLOAD), env={"PATH": str(bin_dir)})
    assert proc.returncode == 0
    assert proc.stdout == b"mine\n"
    assert read_usage_from_cache(str(cache))["session_pct"] == 42


@pytest.mark.parametrize("stdin, cached", [
    (b'{"a": 1}', True),
    (b'\n  \t{"a": 1}\n', True),
    (b'  [1, 2]', False),
    (b'   ', False),
    (b'"{"', False),
])
def test_sh_bridge_caches_only_input_whose_first_nonblank_char_is_a_brace(
        sh_bridge, stdin, cached):
    proc, cache = sh_bridge.run(stdin)
    assert proc.returncode == 0
    assert cache.exists() is cached
    if cached:
        assert cache.read_bytes() == stdin


def test_sh_bridge_passes_stdin_to_the_original_byte_for_byte(sh_bridge):
    payload = b'{"text": "caf\xc3\xa9 \\u00e9", "n": 1}\n\n'
    proc, cache = sh_bridge.run(
        payload, original={"statusLine": {"type": "command", "command": "cat"}})
    assert proc.stdout == payload
    assert cache.read_bytes() == payload


def test_sh_bridge_runs_the_saved_command_verbatim(sh_bridge):
    # Quotes, backslashes, a dollar sign and a newline would not survive a
    # hand-rolled JSON string extraction; the plain-text sidecar keeps them.
    command = 'printf \'%s|\' "it\'s \\"q\\" \\\\ $HOME"\necho done'
    proc, _ = sh_bridge.run(
        json.dumps(PAYLOAD),
        original={"statusLine": {"type": "command", "command": command}},
        env={"HOME": "/h"},
    )
    assert proc.stdout == b'it\'s "q" \\ /h|done\n'


@pytest.mark.parametrize("sidecar", ["", "   \n", "\n\n"])
def test_sh_bridge_ignores_an_empty_saved_command(sh_bridge, sidecar):
    (sh_bridge.clawd_dir / hooks.STATUSLINE_COMMAND_NAME).write_text(sidecar)
    proc, cache = sh_bridge.run(json.dumps(PAYLOAD))
    assert proc.returncode == 0
    assert proc.stdout == b""
    assert cache.exists()


def test_sh_bridge_never_prints_errors(sh_bridge):
    (sh_bridge.clawd_dir / "statusline-cache.json").mkdir()
    proc, _ = sh_bridge.run(
        json.dumps(PAYLOAD),
        original={"statusLine": {"type": "command", "command": "echo out; echo err >&2; exit 3"}},
    )
    assert proc.returncode == 0
    assert proc.stdout == b"out\n"
    assert proc.stderr == b""


def test_sh_bridge_creates_the_dir_and_keeps_the_cache_private(sh_bridge):
    fresh = sh_bridge.clawd_dir / "new" / "dir"
    proc, _ = sh_bridge.run(json.dumps(PAYLOAD), env={"CLAWD_TANK_DIR": str(fresh)})
    assert proc.returncode == 0
    assert (fresh / "statusline-cache.json").stat().st_mode & 0o777 == 0o600


def test_sh_bridge_defaults_to_the_clawd_dir_under_home(sh_bridge, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home)}
    env.pop("CLAWD_TANK_DIR", None)
    proc = subprocess.run(
        sh_bridge.argv, input=json.dumps(PAYLOAD).encode(),
        capture_output=True, env=env, timeout=30,
    )
    assert proc.returncode == 0
    assert (home / ".clawd-tank" / "statusline-cache.json").exists()


def test_sh_bridge_guard_skips_the_chain_but_still_caches(sh_bridge):
    original = {"statusLine": {"type": "command", "command": "echo chained"}}
    proc, cache = sh_bridge.run(
        json.dumps(PAYLOAD), original=original, env={"CLAWD_TANK_STATUSLINE_BRIDGE": "1"})
    assert proc.stdout == b""
    assert cache.exists()


def test_sh_bridge_marks_the_chained_command_with_the_guard(sh_bridge):
    proc, _ = sh_bridge.run(
        json.dumps(PAYLOAD),
        original={"statusLine": {"type": "command",
                                 "command": 'printf %s "$CLAWD_TANK_STATUSLINE_BRIDGE"'}},
    )
    assert proc.stdout == b"1"


def test_sh_bridge_stops_a_hung_original_after_the_timeout(sh_bridge):
    started = time.monotonic()
    proc, cache = sh_bridge.run(
        json.dumps(PAYLOAD),
        original={"statusLine": {"type": "command", "command": "sleep 30; echo late"}},
        env={"CLAWD_TANK_STATUSLINE_TIMEOUT": "1"},
        timeout=15,
    )
    assert time.monotonic() - started < 10
    assert proc.returncode == 0
    assert b"late" not in proc.stdout
    assert cache.exists()


def test_sh_bridge_does_not_wait_for_the_timeout_when_the_original_is_quick(sh_bridge):
    started = time.monotonic()
    proc, _ = sh_bridge.run(
        json.dumps(PAYLOAD),
        original={"statusLine": {"type": "command", "command": "echo quick"}},
        env={"CLAWD_TANK_STATUSLINE_TIMEOUT": "20"},
        timeout=15,
    )
    assert time.monotonic() - started < 10
    assert proc.stdout == b"quick\n"


@pytest.mark.parametrize("bad", ["", "abc", "-1", "1;reboot"])
def test_sh_bridge_falls_back_to_the_default_timeout_for_a_bad_value(sh_bridge, bad):
    proc, _ = sh_bridge.run(
        json.dumps(PAYLOAD),
        original={"statusLine": {"type": "command", "command": "echo fine"}},
        env={"CLAWD_TANK_STATUSLINE_TIMEOUT": bad},
    )
    assert proc.stdout == b"fine\n"


# --- which shell the Python bridge chains the original through ----------------
#
# Claude Code on Windows runs statusLine commands through Git Bash, so the user's
# original (written for bash: `~/.claude/statusline.sh`, `$HOME`, forward-slash
# paths) must go through the same bash. cmd.exe, the plain shell=True, is only
# the fallback. The selection takes the platform and environment as arguments so
# it can be checked here, where Windows is not available.

GIT_BASH = "C:\\Program Files\\Git\\bin\\bash.exe"
GIT_CMD_EXE = "C:\\Program Files\\Git\\cmd\\git.exe"
WSL_LAUNCHER = "C:\\Windows\\System32\\bash.exe"


def test_python_bridge_script_compiles_without_warnings():
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # e.g. an invalid escape in a docstring
        compile(hooks.STATUSLINE_BRIDGE_SCRIPT, "statusline_bridge.py", "exec")


@pytest.fixture(scope="module")
def bridge_module():
    namespace = {"__name__": "statusline_bridge_under_test"}
    exec(compile(hooks.STATUSLINE_BRIDGE_SCRIPT, "statusline_bridge.py", "exec"), namespace)
    return namespace


def _invocation(module, platform, *, env=None, existing=(), path=None, cwd="C:\\work\\repo",
                command="orig --x"):
    """chain_invocation result. `path` is the PATH value; `existing` the files that exist."""
    environ = dict(env or {})
    if path is not None:
        environ["PATH"] = path
    return module["chain_invocation"](
        command, platform, environ, lambda p: p in existing, cwd)


GIT_PATH = "C:\\Program Files\\Git\\cmd"


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_posix_keeps_chaining_through_the_default_shell(bridge_module, platform):
    result = _invocation(
        bridge_module, platform, env={"CLAUDE_CODE_GIT_BASH_PATH": GIT_BASH},
        existing={GIT_BASH, GIT_CMD_EXE}, path=GIT_PATH)
    assert result == ("orig --x", True)


def test_windows_uses_the_git_bash_claude_code_was_told_to_use(bridge_module):
    custom = "D:\\tools\\git\\bin\\bash.exe"
    result = _invocation(
        bridge_module, "win32", env={"CLAUDE_CODE_GIT_BASH_PATH": custom},
        existing={custom, GIT_BASH, GIT_CMD_EXE}, path=GIT_PATH)
    assert result == ([custom, "-c", "orig --x"], False)


def test_windows_ignores_a_configured_bash_that_is_not_there(bridge_module):
    result = _invocation(
        bridge_module, "win32", env={"CLAUDE_CODE_GIT_BASH_PATH": "D:\\gone\\bash.exe"},
        existing={GIT_BASH, GIT_CMD_EXE}, path=GIT_PATH)
    assert result == ([GIT_BASH, "-c", "orig --x"], False)


@pytest.mark.parametrize("configured", [
    "bash.exe",                       # relative: resolved against the project cwd
    "bin\\bash.exe",
    ".\\bash.exe",
    "C:bash.exe",                     # drive-relative
    "C:\\Windows\\System32\\cmd.exe",   # absolute and present, but not bash.exe
    "C:\\Program Files\\Git\\bin",      # not a bash.exe
])
def test_windows_requires_the_configured_bash_to_be_an_absolute_bash_exe(bridge_module, configured):
    result = _invocation(
        bridge_module, "win32", env={"CLAUDE_CODE_GIT_BASH_PATH": configured},
        existing={configured, "C:\\work\\repo\\bash.exe"})
    assert result == ("orig --x", True)


@pytest.mark.parametrize("git, bash", [
    # the default Git for Windows layout: git.exe in cmd\, bash.exe in bin\
    (GIT_CMD_EXE, GIT_BASH),
    # git.exe from mingw64\bin: bash is two folders up, in bin\
    ("C:\\Program Files\\Git\\mingw64\\bin\\git.exe", GIT_BASH),
    # a portable layout with both side by side
    ("D:\\PortableGit\\bin\\git.exe", "D:\\PortableGit\\bin\\bash.exe"),
])
def test_windows_finds_the_bash_that_ships_next_to_git(bridge_module, git, bash):
    result = _invocation(
        bridge_module, "win32", existing={git, bash}, path="C:\\Windows;" + ntpath_dirname(git))
    assert result == ([bash, "-c", "orig --x"], False)


def ntpath_dirname(p):
    import ntpath
    return ntpath.dirname(p)


def test_windows_never_takes_a_bash_off_the_path(bridge_module):
    # System32\bash.exe is the WSL launcher: it would run the command in Linux.
    result = _invocation(
        bridge_module, "win32", existing={WSL_LAUNCHER, GIT_CMD_EXE},
        path="C:\\Windows\\System32;" + GIT_PATH)
    assert result == ("orig --x", True)


def test_windows_without_git_or_bash_falls_back_to_the_default_shell(bridge_module):
    assert _invocation(bridge_module, "win32") == ("orig --x", True)
    assert _invocation(bridge_module, "win32", existing={GIT_CMD_EXE}, path="C:\\bin") == ("orig --x", True)
    # git found but no bash.exe in a Git for Windows layout
    assert _invocation(bridge_module, "win32", existing={GIT_CMD_EXE}, path=GIT_PATH) == ("orig --x", True)


def test_windows_ignores_a_git_planted_in_the_current_directory(bridge_module):
    cwd = "C:\\work\\repo"
    planted = {cwd + "\\git.exe", cwd + "\\bash.exe", cwd + "\\bin\\bash.exe"}
    # PATH has the cwd explicitly, in a different case and with a trailing slash
    result = _invocation(bridge_module, "win32", existing=planted, cwd=cwd,
                         path="c:\\WORK\\repo\\;")
    assert result == ("orig --x", True)
    # an empty PATH entry means "current directory" to some Windows lookups
    assert _invocation(bridge_module, "win32", existing=planted, cwd=cwd, path=";") == ("orig --x", True)


def test_windows_ignores_a_planted_git_but_still_finds_the_real_one(bridge_module):
    cwd = "C:\\work\\repo"
    existing = {cwd + "\\git.exe", cwd + "\\bin\\bash.exe", GIT_CMD_EXE, GIT_BASH}
    result = _invocation(bridge_module, "win32", existing=existing, cwd=cwd,
                         path=cwd + ";" + GIT_PATH)
    assert result == ([GIT_BASH, "-c", "orig --x"], False)


@pytest.mark.parametrize("entry", ["Git\\cmd", ".\\Git\\cmd", "..\\Git\\cmd", "C:Git\\cmd", "."])
def test_windows_ignores_relative_path_entries(bridge_module, entry):
    cwd = "C:\\work\\repo"
    existing = {cwd + "\\Git\\cmd\\git.exe", cwd + "\\Git\\bin\\bash.exe",
                "Git\\cmd\\git.exe", "Git\\bin\\bash.exe"}
    result = _invocation(bridge_module, "win32", existing=existing, cwd=cwd, path=entry)
    assert result == ("orig --x", True)
