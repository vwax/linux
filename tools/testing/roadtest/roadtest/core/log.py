# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from pathlib import Path
from typing import Iterable


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

    def get_last_log(self) -> list[str]:
        try:
            startpos = next(
                i for i, line in enumerate(reversed(self.lines)) if "STOP<" in line
            )
            return self.lines[-startpos:]
        except StopIteration:
            pass

        try:
            startpos = next(
                i for i, line in enumerate(reversed(self.lines)) if "START<" in line
            )
            return self.lines[-startpos:]
        except StopIteration:
            pass

        return self.lines

    def _get_containing_logs(self, lines: list[str], pos: int) -> list[str]:
        startpos = 0
        stoppos = len(lines)

        for i in range(pos, 0, -1):
            if "STOP<" in lines[i]:
                startpos = i + 1
                break
            if "START<" in lines[i]:
                startpos = i
                break

        for i in range(pos, len(lines)):
            if "START<" in lines[i]:
                stoppos = i
                break
            if "STOP<" in lines[i]:
                stoppos = i + 1
                break

        return lines[startpos:stoppos]

    def get_warning_logs(self) -> Iterable[tuple[str, list[str]]]:
        if "WARNING" not in self.raw:
            return

        lines = self.lines
        while True:
            try:
                pos, line = next(
                    (i, line) for i, line in enumerate(lines) if "WARNING" in line
                )
            except StopIteration:
                break

            yield line, self._get_containing_logs(lines, pos)

            lines = lines[pos + 1 :]
