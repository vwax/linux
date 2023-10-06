# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import enum
import logging
import typing
from typing import Optional

from roadtest.core.devicetree import GpioPin

# Import only during type checking to avoid circular imports
if typing.TYPE_CHECKING:
    from .backend import Backend

logger = logging.getLogger(__name__)


class IrqType(enum.IntEnum):
    NONE = 0x00
    EDGE_RISING = 0x01
    EDGE_FALLING = 0x02
    EDGE_BOTH = 0x03
    LEVEL_HIGH = 0x04
    LEVEL_LOW = 0x08


class Gpio:
    def __init__(self, backend: "Backend", pin: int):
        self.backend = backend
        self.pin = pin
        self.state = False
        self.irq_type = IrqType.NONE
        self.masked = True
        self.edge_irq_latched = False

    def _level_irq_active(self) -> bool:
        if self.irq_type == IrqType.LEVEL_HIGH:
            return self.state
        elif self.irq_type == IrqType.LEVEL_LOW:
            return not self.state

        return False

    def _latch_edge_irq(self, old: bool, new: bool) -> bool:
        if self.irq_type == IrqType.EDGE_RISING:
            return not old and new
        elif self.irq_type == IrqType.EDGE_FALLING:
            return old and not new
        elif self.irq_type == IrqType.EDGE_BOTH:
            return old != new

        return False

    def _check_irq(self) -> None:
        if self.irq_type == IrqType.NONE or self.masked:
            return
        if not self.edge_irq_latched and not self._level_irq_active():
            return

        self.masked = True
        self.edge_irq_latched = False

        logger.debug(f"{self}: trigger irq")
        self.backend.trigger_gpio_irq(self.pin)

    def set_irq_type(self, rawtype: int) -> None:
        irq_type = IrqType(rawtype)
        logger.debug(f"{self}: set_irq_type {irq_type.name}")
        if irq_type == IrqType.NONE:
            self.masked = True

        self.irq_type = irq_type
        self.edge_irq_latched = False
        self._check_irq()

    def unmask(self) -> None:
        logger.debug(f"{self}: unmask")
        self.masked = False
        self._check_irq()

    def set(self, val: int) -> None:
        old = self.state
        new = bool(val)

        if old != new:
            logger.debug(f"{self}: type={self.irq_type.name} set {old} -> {new}")

        self.state = new
        if self._latch_edge_irq(old, new):
            logger.debug(f"{self}: latching edge")
            self.edge_irq_latched = True

        self._check_irq()

    def __str__(self) -> str:
        return f"Gpio({self.pin})"


class GpioBackend:
    def __init__(self, backend: "Backend") -> None:
        self.backend = backend
        self.gpios = [Gpio(backend, pin) for pin in range(64)]

    def set(self, pin: Optional[GpioPin], val: bool) -> None:
        if pin is None:
            return

        self.gpios[pin.val].set(val)

    def set_irq_type(self, pin: int, irq_type: int) -> None:
        self.gpios[pin].set_irq_type(irq_type)

    def set_value(self, pin: int, value: int) -> None:
        self.backend.mock.gpio_set_value(pin, value)

    def unmask(self, pin: int) -> None:
        self.gpios[pin].unmask()
