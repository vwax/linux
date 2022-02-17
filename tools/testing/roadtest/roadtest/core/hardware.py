# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import contextlib
import functools
import os
from pathlib import Path
from typing import Any, Callable, Optional, Type, cast
from unittest import TestCase
from unittest.mock import MagicMock, call

from roadtest import ENV_WORK_DIR

from .control import ControlWriter
from .opslog import OpsLogReader
from .sysfs import write_int


class HwMock(MagicMock):
    def assert_reg_write_once(self, test: TestCase, reg: int, value: int) -> None:
        test.assertEqual(
            [c for c in self.mock_calls if c.args[0] == reg],
            [call.reg_write(reg, value)],
        )

    def assert_last_reg_write(self, test: TestCase, reg: int, value: int) -> None:
        test.assertEqual(
            [c for c in self.mock_calls if c.args[0] == reg][-1:],
            [call.reg_write(reg, value)],
        )

    def get_last_reg_write(self, reg: int) -> int:
        return cast(int, [c for c in self.mock_calls if c.args[0] == reg][-1].args[1])


class Hardware(contextlib.AbstractContextManager):
    def __init__(self, bus: str, work: Optional[Path] = None) -> None:
        if not work:
            work = Path(os.environ[ENV_WORK_DIR])

        self.bus = bus
        self.mock = HwMock()
        self.control = ControlWriter(work)
        self.opslog = OpsLogReader(work)
        self.loaded_model = False

        # Ignore old entries
        self.opslog.read_next()

    def _call(self, method: str, *args: Any, **kwargs: Any) -> None:
        self.control.write_cmd(
            f"backend.{self.bus}.{method}(*{str(args)}, **{str(kwargs)})"
        )

    def kick(self) -> None:
        # Control writes are only applied when the backend gets something
        # to process, usually because the driver tried to access the device.
        # But in some cases, such as when the driver is waiting for a
        # sequence of interrupts, the test code needs the control write to take
        # effect immediately.  For this, we just need to kick the backend
        # into processing its control queue.
        #
        # We (ab)use gpio-leds for this.  devicetree.py sets up the device.
        write_int(Path("/sys/class/leds/led0/brightness"), 0)

    def load_model(self, cls: Type[Any], *args: Any, **kwargs: Any) -> "Hardware":
        self._call("load_model", cls.__module__, cls.__name__, *args, **kwargs)
        self.loaded_model = True
        return self

    def __enter__(self) -> "Hardware":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @functools.cache
    def __getattr__(self, name: str) -> Callable:
        def func(*args: Any, **kwargs: Any) -> None:
            self._call(name, *args, **kwargs)

        return func

    def close(self) -> None:
        if self.loaded_model:
            self._call("unload_model")
        self.control.close()

    def update_mock(self) -> HwMock:
        opslog = self.opslog.read_next()
        for line in opslog:
            eval(line, {"mock": self.mock})

        return self.mock
