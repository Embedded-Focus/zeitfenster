import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

ENTRYPOINT = Path(__file__).parents[1] / "docker" / "entrypoint.sh"


@pytest.fixture
def entrypoint_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    sleep_log = tmp_path / "sleep.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_sleep = bin_dir / "sleep"
    fake_sleep.write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$SLEEP_LOG"\n')
    fake_sleep.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["SLEEP_LOG"] = str(sleep_log)
    return env, sleep_log


@pytest.mark.parametrize(
    ("command_status", "expected_sleep"),
    [(0, None), (7, "5\n")],
)
def test_entrypoint_backs_off_only_after_failure(
    entrypoint_env: tuple[dict[str, str], Path],
    command_status: int,
    expected_sleep: str | None,
):
    env, sleep_log = entrypoint_env

    result = subprocess.run(
        [ENTRYPOINT, "/bin/sh", "-c", f"exit {command_status}"],
        env=env,
        check=False,
    )

    assert result.returncode == command_status
    if expected_sleep is None:
        assert not sleep_log.exists()
    else:
        assert sleep_log.read_text() == expected_sleep


def test_entrypoint_forwards_sigterm_and_exits_cleanly(
    entrypoint_env: tuple[dict[str, str], Path],
    tmp_path: Path,
):
    env, sleep_log = entrypoint_env
    ready = tmp_path / "ready"
    terminated = tmp_path / "terminated"
    child_code = textwrap.dedent(
        """
        import signal
        import sys
        from pathlib import Path

        terminated = Path(sys.argv[1])
        ready = Path(sys.argv[2])

        def handle_sigterm(signum, frame):
            terminated.touch()
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, handle_sigterm)
        ready.touch()
        signal.pause()
        """
    )
    process = subprocess.Popen(
        [ENTRYPOINT, sys.executable, "-c", child_code, terminated, ready],
        env=env,
    )

    try:
        deadline = time.monotonic() + 5
        while not ready.exists():
            if process.poll() is not None:
                pytest.fail("entrypoint exited before its child was ready")
            if time.monotonic() >= deadline:
                pytest.fail("entrypoint child did not become ready")
            time.sleep(0.01)

        process.terminate()
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()

    assert terminated.exists()
    assert not sleep_log.exists()
