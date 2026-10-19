#!/usr/bin/env python3
"""Cross-platform launcher for Windows, macOS and Linux.

Mac and Linux keep using ./start.sh. Windows uses start.bat.
Both commands run this file. It creates the virtual environment in the
layout of the current system, installs requirements when they change,
and starts the app on 127.0.0.1:8000.
"""
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / "venv"
REQUIREMENTS = ROOT / "requirements.txt"
STAMP_FILE = VENV_DIR / ".requirements-installed"
HOST = "127.0.0.1"
PORT = 8000
MIN_PYTHON = (3, 10)
MAX_PYTHON = (3, 13)


def python_version_supported(version):
    return version is not None and MIN_PYTHON <= version <= MAX_PYTHON


def venv_python():
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def running_in_project_venv():
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


def invocation_version(argv):
    try:
        output = subprocess.check_output(
            argv + ["-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=20,
        ).strip()
        major, minor = output.split(".")
        return int(major), int(minor)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None


def iter_python_invocations():
    if sys.executable:
        yield [sys.executable]
    if os.name == "nt":
        for minor in range(MAX_PYTHON[1], MIN_PYTHON[1] - 1, -1):
            yield ["py", "-3.%d" % minor]
        return
    for name in ("python3.13", "python3.12", "python3.11", "python3.10", "python3", "python"):
        found = shutil.which(name)
        if found:
            yield [found]


def find_base_python():
    for argv in iter_python_invocations():
        version = invocation_version(argv)
        if python_version_supported(version):
            return argv
    return None


def port_is_free(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def restart_command():
    if os.name == "nt":
        return "start.bat"
    return "./start.sh"


def say(message=""):
    print(message, flush=True)


def print_port_help():
    say("Port %d is already in use." % PORT)
    say("This launcher does not stop the other program.")
    say("If Nearletter is already open, use it at http://%s:%d" % (HOST, PORT))
    say("or press Stop system on the Dashboard.")
    say("Start it again afterwards with %s" % restart_command())


def ensure_venv():
    existing = venv_python()
    if existing.exists() and python_version_supported(invocation_version([str(existing)])):
        say("Using existing virtual environment: %s" % VENV_DIR.name)
        return
    if VENV_DIR.exists():
        say("Virtual environment is unusable. Recreating it...")
        shutil.rmtree(VENV_DIR)
    base = find_base_python()
    if not base:
        say("No compatible Python found. Install Python 3.10, 3.11, 3.12, or 3.13.")
        say("Python 3.14 is not supported yet because the pinned dependencies do not run on it.")
        if sys.platform.startswith("linux"):
            say("On Debian or Ubuntu also install: sudo apt install python3-venv")
        sys.exit(1)
    say("Creating virtual environment with: %s" % " ".join(base))
    try:
        subprocess.check_call(base + ["-m", "venv", str(VENV_DIR)])
    except subprocess.CalledProcessError:
        say("Could not create the virtual environment.")
        if sys.platform.startswith("linux"):
            say("On Debian or Ubuntu install: sudo apt install python3-venv")
        sys.exit(1)


def install_requirements_if_needed():
    needs_install = not STAMP_FILE.exists()
    if STAMP_FILE.exists() and REQUIREMENTS.exists():
        needs_install = REQUIREMENTS.stat().st_mtime > STAMP_FILE.stat().st_mtime
    if not needs_install:
        say("Requirements already up to date.")
        return
    say("Installing Python requirements...")
    subprocess.check_call([str(venv_python()), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    STAMP_FILE.write_text("ok\n", encoding="utf-8")


def main():
    os.chdir(ROOT)
    if not running_in_project_venv():
        ensure_venv()
        python = str(venv_python())
        os.execv(python, [python, str(ROOT / "start.py")])
    install_requirements_if_needed()
    if not port_is_free(HOST, PORT):
        print_port_help()
        sys.exit(1)
    say("")
    say("  Nearletter starting...")
    say("  http://%s:%d" % (HOST, PORT))
    say("")
    os.execv(
        sys.executable,
        [sys.executable, "-m", "uvicorn", "main:app", "--host", HOST, "--port", str(PORT)],
    )


if __name__ == "__main__":
    main()
