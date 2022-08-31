# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from pathlib import Path
from tempfile import NamedTemporaryFile

from roadtest.core.log import LogParser


def test_parser() -> None:
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

        assert parser.has_any()
        assert parser.get_testcase_log("finished") == ["finished1", "finished2"]

        assert parser.get_testcase_log("unfinished") == [
            "unfinished1",
            "unfinished2",
            LogParser.DNF_MESSAGE,
        ]

        assert not parser.get_testcase_log("notpresent")
        assert not parser.get_testcase_log("empty")

        # START/STOP on the same line shouldn't really happen since
        # we print via /dev/kmsg.
        assert not parser.get_testcase_log("foo")


def test_warnings() -> None:
    with NamedTemporaryFile() as tmpfile:
        path = Path(tmpfile.name)

        path.write_text(
            """
WARNING: a
more a
START<b>
WARNING: b
more b
STOP<b>
WARNING: c
more c""".lstrip()
        )

        parser = LogParser(path)

        warnings = list(parser.get_warning_logs())
        assert warnings[0] == ("WARNING: a", ["WARNING: a", "more a"])
        assert warnings[1] == (
            "WARNING: b",
            ["START<b>", "WARNING: b", "more b", "STOP<b>"],
        )
        assert warnings[2] == ("WARNING: c", ["WARNING: c", "more c"])


def test_parser_not_found() -> None:
    parser = LogParser(Path("/roadtest_does_not_exist"))
    assert not parser.has_any()
    assert not parser.get_testcase_log("foo")
