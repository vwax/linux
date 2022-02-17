# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from roadtest.backend.mock import MockBackend

from .hardware import Hardware


class TestHardware(TestCase):
    def test_mock(self) -> None:
        with TemporaryDirectory() as tmpdir:
            work = Path(tmpdir)

            backend = MockBackend(work)
            hw = Hardware(bus="dummy", work=work)

            backend.reg_write(0x1, 0xDEAD)
            backend.reg_write(0x2, 0xBEEF)
            mock = hw.update_mock()
            mock.assert_reg_write_once(self, 0x1, 0xDEAD)

            backend.reg_write(0x1, 0xCAFE)
            mock = hw.update_mock()
            with self.assertRaises(AssertionError):
                mock.assert_reg_write_once(self, 0x1, 0xDEAD)

            mock.assert_last_reg_write(self, 0x1, 0xCAFE)

            self.assertEqual(mock.get_last_reg_write(0x1), 0xCAFE)
            self.assertEqual(mock.get_last_reg_write(0x2), 0xBEEF)

            with self.assertRaises(IndexError):
                self.assertEqual(mock.get_last_reg_write(0x3), 0x0)

            mock.reset_mock()
            with self.assertRaises(AssertionError):
                mock.assert_last_reg_write(self, 0x2, 0xBEEF)
