from typing import Any, cast

import pytest

from roadtest.core.control import ControlProxy, ControlWriter
from roadtest.pytest.host import ResultStreamHost


class TargetPlugin:
    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        self.resultstream = ControlWriter(filename="resultstream.txt")

        self.host = cast(ResultStreamHost, ControlProxy(call=self._call_result))
        self.kmsg = open("/dev/kmsg", "w", buffering=1)
        self.control = ControlWriter()

    def _call_result(self, method: str, *args: Any, **kwargs: Any) -> None:
        self.resultstream.write_cmd(f"result.{method}(*{str(args)}, **{str(kwargs)})")

    def _log(self, nodeid: str, action: str) -> None:
        line = f"{action}<{nodeid}>"
        self.kmsg.write(line + "\n")
        self.control.write_log(line)

    def pytest_runtest_logstart(self, nodeid: str, location: tuple) -> None:
        self._log(nodeid, "START")
        self.host.logstart(nodeid, location)

    def pytest_runtest_logfinish(self, nodeid: str, location: tuple) -> None:
        self._log(nodeid, "STOP")
        self.host.logfinish(nodeid, location)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        data = self.config.hook.pytest_report_to_serializable(
            config=self.config, report=report
        )
        self.host.logreport(data)


def pytest_configure(config: pytest.Config) -> None:
    config.pluginmanager.register(TargetPlugin(config), "roadtest-remote")
