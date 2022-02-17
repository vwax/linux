# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest import TestCase

from .log import LogParser


class TestLog(TestCase):
    def test_parser(self) -> None:
        with NamedTemporaryFile() as tmpfile:
            path = Path(tmpfile.name)

            path.write_text(
                """
xyz START<finished>
finished1
finished2
STOP<finished>
START<empty>
STOP<empty>
START<foo> monkey STOP<foo>
START<unfinished>
unfinished1
unfinished2"""
            )

            parser = LogParser(path)
            self.assertEqual(
                parser.get_testcase_log("finished"), ["finished1", "finished2"]
            )

            self.assertEqual(
                parser.get_testcase_log("unfinished"),
                ["unfinished1", "unfinished2", LogParser.DNF_MESSAGE],
            )

            self.assertEqual(
                parser.get_testcase_log("notpresent"),
                [],
            )

            self.assertEqual(
                parser.get_testcase_log("enpty"),
                [],
            )

            # Shouldn't happen since we print from the kernel?
            self.assertEqual(
                parser.get_testcase_log("foo"),
                [],
            )
