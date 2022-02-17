# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from .control import ControlReader, ControlWriter


class TestControl(TestCase):
    def test_control(self) -> None:
        with TemporaryDirectory() as tmpdir:
            work = Path(tmpdir)
            reader = ControlReader(work)
            writer = ControlWriter(work)

            values = []

            def append(new: int) -> None:
                nonlocal values
                values.append(new)

            vars = {"append": append}
            writer.write_cmd("append(1)")

            reader.process(vars)
            self.assertEqual(values, [1])

            writer.write_cmd("append(2)")
            writer.write_log("append(4)")
            writer.write_cmd("append(3)")

            reader.process(vars)
            self.assertEqual(values, [1, 2, 3])
