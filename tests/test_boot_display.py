import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_boot_probe import read_display_number


@unittest.skipUnless(os.name == "posix", "Internal Linux display helper")
class BootDisplayTests(unittest.TestCase):
    def test_split_server_notification_keeps_pipe_open_until_newline(self):
        read_fd, write_fd = os.pipe()
        first_read = threading.Event()
        failures = []
        original_read = os.read

        def read(fd, size):
            data = original_read(fd, size)
            if fd == read_fd and data == b"12":
                first_read.set()
            return data

        def server():
            try:
                os.write(write_fd, b"12")
                if not first_read.wait(2):
                    raise RuntimeError("Reader did not consume the display digits")
                os.write(write_fd, b"\n")
            except Exception as error:
                failures.append(error)
            finally:
                os.close(write_fd)

        thread = threading.Thread(target=server)
        thread.start()
        try:
            with patch("run_boot_probe.os.read", side_effect=read):
                self.assertEqual(read_display_number(read_fd, 3), "12")
        finally:
            os.close(read_fd)
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])

    def test_closed_incomplete_notification_rejects(self):
        read_fd, write_fd = os.pipe()
        os.write(write_fd, b"1")
        os.close(write_fd)
        try:
            with self.assertRaisesRegex(ValueError, "display failed"):
                read_display_number(read_fd)
        finally:
            os.close(read_fd)

    def test_invalid_and_overlong_notifications_reject(self):
        for data in (b"\n", b"abc\n", b"1\n2\n", b"1" * 33 + b"\n"):
            with self.subTest(data=data):
                read_fd, write_fd = os.pipe()
                os.write(write_fd, data)
                os.close(write_fd)
                try:
                    with self.assertRaises(ValueError):
                        read_display_number(read_fd)
                finally:
                    os.close(read_fd)

    def test_notification_deadline_rejects_without_data(self):
        read_fd, write_fd = os.pipe()
        try:
            with self.assertRaisesRegex(ValueError, "did not start"):
                read_display_number(read_fd, .01)
        finally:
            os.close(read_fd)
            os.close(write_fd)
