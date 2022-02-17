# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from pathlib import Path


class LogParser:
    DNF_MESSAGE = "<Test did not finish cleanly>"

    def __init__(self, file: Path):
        try:
            raw = file.read_text()
            lines = raw.splitlines()
        except FileNotFoundError:
            lines = []
            raw = ""

        self.raw = raw
        self.lines = lines

    def has_any(self) -> bool:
        return "START<" in self.raw

    def get_testcase_log(self, id: str) -> list[str]:
        startmarker = f"START<{id}>"
        stopmarker = f"STOP<{id}>"

        try:
            startpos = next(
                i for i, line in enumerate(self.lines) if startmarker in line
            )
        except StopIteration:
            return []

        try:
            stoppos = next(
                i for i, line in enumerate(self.lines[startpos:]) if stopmarker in line
            )
        except StopIteration:
            return self.lines[startpos + 1 :] + [LogParser.DNF_MESSAGE]

        return self.lines[startpos + 1 : startpos + stoppos]
