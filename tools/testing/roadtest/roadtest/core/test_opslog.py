# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from .opslog import OpsLogReader, OpsLogWriter


class TestOpsLOg(TestCase):
    def test_opslog(self) -> None:
        with TemporaryDirectory() as tmpdir:
            work = Path(tmpdir)
            writer = OpsLogWriter(work)
            reader = OpsLogReader(work)

            self.assertEqual(reader.read_next(), [])

            writer.write("1")
            writer.write("2")

            self.assertEqual(reader.read_next(), ["1", "2"])
            self.assertEqual(reader.read_next(), [])

            writer.write("3")
            self.assertEqual(reader.read_next(), ["3"])
