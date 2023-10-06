# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import contextlib
import os
from functools import partial
from pathlib import Path
from typing import Any, Generic, Optional, Type, TypeVar, cast
from unittest.mock import MagicMock, call

from roadtest import ENV_WORK_DIR
from roadtest.backend.i2c import I2CModel
from roadtest.backend.platform import PlatformModel
from roadtest.backend.serial import SerialModel
from roadtest.backend.spi import SPIModel
from roadtest.core.control import ControlProxy, ControlWriter
from roadtest.core.devicetree import GpioPin
from roadtest.core.opslog import OpsLogReader
from roadtest.support.sysfs import write_int


class HwMock(MagicMock):
    def assert_reg_write_once(self, reg: int, value: int) -> None:
        assert [c for c in self.mock_calls if c.args[0] == reg] == [
            call.reg_write(reg, value)
        ]

    def assert_last_reg_write(self, reg: int, value: int) -> None:
        assert [c for c in self.mock_calls if c.args[0] == reg][-1:] == [
            call.reg_write(reg, value)
        ]

    def get_last_reg_write(self, reg: int) -> int:
        writes = [c for c in self.mock_calls if c.args[0] == reg]
        # Something more friendly than IndexError
        assert writes, f"{reg=:#x} not written"

        return cast(int, writes[-1].args[1])

    def assert_last_reg_write_mask(self, reg: int, *, mask: int, value: int) -> None:
        gotval = self.get_last_reg_write(reg)
        assert gotval & mask == value & mask

    def assert_last_reg_set_mask(self, reg: int, mask: int) -> None:
        self.assert_last_reg_write_mask(reg, mask=mask, value=~0)

    def assert_last_reg_clear_mask(self, reg: int, mask: int) -> None:
        self.assert_last_reg_write_mask(reg, mask=mask, value=0)


# These TypeVars (and the bound TypeVars of the individual busses) make
# it possible for type checkers to see through calls from the test cases
# to the models even though in reality the model and the tests run on
# different systems cannot communicate directly.
ModelT = TypeVar("ModelT")
HardwareT = TypeVar("HardwareT", bound="Hardware")


class Hardware(Generic[ModelT], contextlib.AbstractContextManager):
    def __init__(self, bus: str, work: Optional[Path] = None) -> None:
        if not work:
            work = Path(os.environ[ENV_WORK_DIR])

        self.bus = bus
        self.control = ControlWriter(work)
        self.opslog = OpsLogReader(work)
        self.loaded_model = False

        # Make the proxy transparent to type checkers.
        self.model = cast(
            ModelT, ControlProxy(name="model", call=partial(self._call, self.bus))
        )

        # Ignore old entries
        self.opslog.read_next()

        self.fault_injecting = False

    def _call(self, obj: str, method: str, *args: Any, **kwargs: Any) -> None:
        self.control.write_cmd(f"backend.{obj}.{method}(*{str(args)}, **{str(kwargs)})")

    def log(self, line: str) -> None:
        self.control.write_log(line)

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

    def load_model(
        self: HardwareT, cls: Type[ModelT], *args: Any, **kwargs: Any
    ) -> HardwareT:
        self._call(
            self.bus, "load_model", cls.__module__, cls.__name__, *args, **kwargs
        )
        self.loaded_model = True
        return self

    def __enter__(self: HardwareT) -> HardwareT:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        if self.loaded_model:
            self._call(self.bus, "unload_model")
        self.control.close()

    def update_mock(self, mock: Optional[HwMock] = None) -> HwMock:
        mock = mock if mock is not None else HwMock()
        opslog = self.opslog.read_next()
        for line in opslog:
            eval(line, {"mock": mock})

        return mock


I2CModelT = TypeVar("I2CModelT", bound=I2CModel)


class I2CHardware(Hardware[I2CModelT]):
    def __init__(self, cls: Type[I2CModelT], *args: Any, **kwargs: Any):
        super().__init__("i2c")
        self.load_model(cls, *args, **kwargs)


SPIModelT = TypeVar("SPIModelT", bound=SPIModel)


class SPIHardware(Hardware[SPIModelT]):
    def __init__(self, cls: Type[SPIModelT], *args: Any, **kwargs: Any):
        super().__init__("i2c")
        self.load_model(cls, *args, **kwargs)


SerialModelT = TypeVar("SerialModelT", bound=SerialModel)


class SerialHardware(Hardware[SerialModelT]):
    def __init__(self, cls: Type[SerialModelT], *args: Any, **kwargs: Any):
        super().__init__("i2c")
        # Gpio 1 is reserved for this by the allocator
        kwargs["bridge_irq"] = GpioPin(1)
        self.load_model(cls, *args, **kwargs)


PlatformModelT = TypeVar("PlatformModelT", bound=PlatformModel)


class PlatformHardware(Hardware[PlatformModelT]):
    def __init__(self, cls: Type[PlatformModelT], *args: Any, **kwargs: Any):
        super().__init__("platform")
        self.load_model(cls, *args, **kwargs)


class NoBusHardware(Hardware):
    def __init__(self) -> None:
        super().__init__("dummy")
