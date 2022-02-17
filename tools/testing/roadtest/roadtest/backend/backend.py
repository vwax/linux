# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import logging
import os
from pathlib import Path

from roadtest import ENV_WORK_DIR
from roadtest.core.control import ControlReader

from . import gpio, i2c, mock

logger = logging.getLogger(__name__)

try:
    import cbackend  # type: ignore[import]
except ModuleNotFoundError:
    # In unit tests
    cbackend = None


class Backend:
    def __init__(self) -> None:
        work = Path(os.environ[ENV_WORK_DIR])
        self.control = ControlReader(work_dir=work)
        self.c = cbackend
        self.i2c = i2c.I2CBackend(self)
        self.gpio = gpio.GpioBackend(self)
        self.mock = mock.MockBackend(work)

    def process_control(self) -> None:
        self.control.process({"backend": self})
