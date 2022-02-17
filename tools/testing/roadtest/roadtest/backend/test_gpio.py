# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import unittest
from unittest.mock import MagicMock

from .gpio import Gpio


class TestGpio(unittest.TestCase):
    def test_irq_low(self) -> None:
        m = MagicMock()
        gpio = Gpio(backend=m, pin=1)

        gpio.set_irq_type(Gpio.IRQ_TYPE_LEVEL_LOW)
        m.c.trigger_gpio_irq.assert_not_called()

        gpio.unmask()
        m.c.trigger_gpio_irq.assert_called_once_with(1)
        m.c.trigger_gpio_irq.reset_mock()

        gpio.set(True)
        gpio.unmask()
        m.c.trigger_gpio_irq.assert_not_called()

    def test_irq_high(self) -> None:
        m = MagicMock()
        gpio = Gpio(backend=m, pin=2)

        gpio.set_irq_type(Gpio.IRQ_TYPE_LEVEL_HIGH)
        gpio.unmask()

        m.c.trigger_gpio_irq.assert_not_called()

        gpio.set(True)
        m.c.trigger_gpio_irq.assert_called_once_with(2)
        m.c.trigger_gpio_irq.reset_mock()

        gpio.set(False)
        gpio.unmask()
        m.c.trigger_gpio_irq.assert_not_called()

    def test_irq_rising(self) -> None:
        m = MagicMock()
        gpio = Gpio(backend=m, pin=63)

        gpio.set_irq_type(Gpio.IRQ_TYPE_EDGE_RISING)
        gpio.set(False)
        gpio.set(True)

        m.c.trigger_gpio_irq.assert_not_called()
        gpio.unmask()
        m.c.trigger_gpio_irq.assert_called_once_with(63)
        m.c.trigger_gpio_irq.reset_mock()

        gpio.set(False)
        gpio.set(True)

        gpio.unmask()
        m.c.trigger_gpio_irq.assert_called_once()

    def test_irq_falling(self) -> None:
        m = MagicMock()
        gpio = Gpio(backend=m, pin=0)

        gpio.set_irq_type(Gpio.IRQ_TYPE_EDGE_FALLING)
        gpio.unmask()
        gpio.set(False)
        gpio.set(True)
        m.c.trigger_gpio_irq.assert_not_called()

        gpio.set(False)
        m.c.trigger_gpio_irq.assert_called_once_with(0)
        m.c.trigger_gpio_irq.reset_mock()

        gpio.set(True)
        gpio.set(False)
        gpio.set(True)
        gpio.unmask()
        m.c.trigger_gpio_irq.assert_called_once()

    def test_irq_both(self) -> None:
        m = MagicMock()
        gpio = Gpio(backend=m, pin=32)

        gpio.set_irq_type(Gpio.IRQ_TYPE_EDGE_BOTH)
        gpio.unmask()
        gpio.set(False)
        gpio.set(True)
        m.c.trigger_gpio_irq.assert_called_once_with(32)

        gpio.set(False)
        m.c.trigger_gpio_irq.assert_called_once_with(32)
        m.c.trigger_gpio_irq.reset_mock()

        gpio.set(True)
        gpio.unmask()
        m.c.trigger_gpio_irq.assert_called_once_with(32)
