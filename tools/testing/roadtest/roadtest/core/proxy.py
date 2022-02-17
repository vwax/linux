# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from typing import Any
from unittest import TestCase, TextTestResult

from . import control


class ProxyTextTestResult(TextTestResult):
    def __init__(self, stream: Any, descriptions: Any, verbosity: Any) -> None:
        super().__init__(stream, descriptions, verbosity)
        self.successes: list[tuple[TestCase, str]] = []

        # Print via kmsg to avoid getting cut off by other kernel prints.
        self.kmsg = open("/dev/kmsg", "w", buffering=1)
        self.control = control.ControlWriter()

    def addSuccess(self, test: TestCase) -> None:
        super().addSuccess(test)
        self.successes.append((test, ""))

    def _log(self, test: TestCase, action: str) -> None:
        line = f"{action}<{test.id()}>"
        self.kmsg.write(line + "\n")
        self.control.write_log(line)

    def startTest(self, test: TestCase) -> None:
        self._log(test, "START")
        super().startTest(test)

    def stopTest(self, test: TestCase) -> None:
        super().stopTest(test)
        self._log(test, "STOP")

    def _replace_id(self, reslist: list[tuple[TestCase, str]]) -> list[tuple[str, str]]:
        return [(case.id(), tb) for case, tb in reslist]

    def to_proxy(self) -> dict[str, Any]:
        return {
            "testsRun": self.testsRun,
            "wasSuccessful": self.wasSuccessful(),
            "successes": self._replace_id(self.successes),
            "errors": self._replace_id(self.errors),
            "failures": self._replace_id(self.failures),
            "skipped": self._replace_id(self.skipped),
            "unexpectedSuccesses": [t.id() for t in self.unexpectedSuccesses],
        }
