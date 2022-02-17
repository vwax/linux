# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import logging
import typing
from typing import Optional

if typing.TYPE_CHECKING:
    # Avoid circular imports
    from .backend import Backend

logger = logging.getLogger(__name__)


class Gpio:
    IRQ_TYPE_NONE = 0x00
    IRQ_TYPE_EDGE_RISING = 0x01
    IRQ_TYPE_EDGE_FALLING = 0x02
    IRQ_TYPE_EDGE_BOTH = 0x03
    IRQ_TYPE_LEVEL_HIGH = 0x04
    IRQ_TYPE_LEVEL_LOW = 0x08

    def __init__(self, backend: "Backend", pin: int):
        self.backend = backend
        self.pin = pin
        self.state = False
        self.irq_type = Gpio.IRQ_TYPE_NONE
        self.masked = True
        self.edge_irq_latched = False

    def _level_irq_active(self) -> bool:
        if self.irq_type == Gpio.IRQ_TYPE_LEVEL_HIGH:
            return self.state
        elif self.irq_type == Gpio.IRQ_TYPE_LEVEL_LOW:
            return not self.state

        return False

    def _latch_edge_irq(self, old: bool, new: bool) -> bool:
        if old != new:
            logger.debug(f"{self}: latch_edge_irq {self.irq_type} {old} -> {new}")

        if self.irq_type == Gpio.IRQ_TYPE_EDGE_RISING:
            return not old and new
        elif self.irq_type == Gpio.IRQ_TYPE_EDGE_FALLING:
            return old and not new
        elif self.irq_type == Gpio.IRQ_TYPE_EDGE_BOTH:
            return old != new

        return False

    def _check_irq(self) -> None:
        if self.irq_type == Gpio.IRQ_TYPE_NONE or self.masked:
            return
        if not self.edge_irq_latched and not self._level_irq_active():
            return

        self.masked = True
        self.edge_irq_latched = False

        logger.debug(f"{self}: trigger irq")
        self.backend.c.trigger_gpio_irq(self.pin)

    def set_irq_type(self, irq_type: int) -> None:
        logger.debug(f"{self}: set_irq_type {irq_type}")
        if irq_type == Gpio.IRQ_TYPE_NONE:
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
            logger.debug(f"{self}: gpio set {old} -> {new}")

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

    def set(self, pin: Optional[int], val: bool) -> None:
        if pin is None:
            return

        self.gpios[pin].set(val)

    def set_irq_type(self, pin: int, irq_type: int) -> None:
        self.gpios[pin].set_irq_type(irq_type)

    def unmask(self, pin: int) -> None:
        self.gpios[pin].unmask()
