import socket
import unittest
from pathlib import Path

import start
from database import resolve_database_url
from routers.system_control import restart_command


class LauncherTests(unittest.TestCase):
    def test_supported_python_range(self):
        self.assertTrue(start.python_version_supported((3, 10)))
        self.assertTrue(start.python_version_supported((3, 13)))
        self.assertFalse(start.python_version_supported((3, 9)))
        self.assertFalse(start.python_version_supported((3, 14)))
        self.assertFalse(start.python_version_supported(None))

    def test_venv_python_matches_this_operating_system(self):
        path = start.venv_python()
        if start.os.name == "nt":
            self.assertEqual(path.name, "python.exe")
            self.assertEqual(path.parent.name, "Scripts")
        else:
            self.assertEqual(path.name, "python")
            self.assertEqual(path.parent.name, "bin")

    def test_port_check_sees_a_bound_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        try:
            self.assertFalse(start.port_is_free("127.0.0.1", port))
        finally:
            sock.close()
        self.assertTrue(start.port_is_free("127.0.0.1", port))

    def test_relative_sqlite_stays_inside_the_project(self):
        root = Path("/tmp/outreach-project")
        resolved = resolve_database_url("sqlite:///./outreach.db", root)
        self.assertTrue(resolved.startswith("sqlite:///"))
        self.assertEqual(
            Path(resolved[len("sqlite:///"):]).resolve(),
            (root / "outreach.db").resolve(),
        )

    def test_absolute_and_memory_sqlite_stay_untouched(self):
        root = Path("/tmp/outreach-project")
        self.assertEqual(
            resolve_database_url("sqlite:////var/data/outreach.db", root),
            "sqlite:////var/data/outreach.db",
        )
        self.assertEqual(resolve_database_url("sqlite:///:memory:", root), "sqlite:///:memory:")

    def test_restart_command_matches_this_operating_system(self):
        expected = "start.bat" if start.os.name == "nt" else "./start.sh"
        self.assertEqual(restart_command(), expected)


if __name__ == "__main__":
    unittest.main()
