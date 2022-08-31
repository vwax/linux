# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import logging
import os
import typing
from pathlib import Path

try:
    import cbackend  # pyright: ignore[reportMissingModuleSource]
except ModuleNotFoundError:
    if not typing.TYPE_CHECKING:
        cbackend = None

from roadtest import ENV_WORK_DIR
from roadtest.core.control import ControlReader

from . import gpio, i2c, mock, platform

logger = logging.getLogger(__name__)

from roadtest.core.devicetree import GpioPin


class Backend:
    def __init__(self) -> None:
        work = Path(os.environ[ENV_WORK_DIR])
        self.control = ControlReader(work_dir=work)
        self.i2c = i2c.I2CBackend(self)
        self.platform = platform.PlatformBackend(self)
        self.gpio = gpio.GpioBackend(self)
        self.mock = mock.MockBackend(work)

    def trigger_gpio_irq(self, pin: int) -> None:
        cbackend.trigger_gpio_irq(pin)

    def dma_read(self, addr: int, len: int) -> bytes:
        return cbackend.dma_read(addr, len)

    def dma_write(self, addr: int, data: bytes) -> None:
        return cbackend.dma_write(addr, data)

    def process_control(self) -> None:
        self.control.process({"backend": self, "GpioPin": GpioPin})
