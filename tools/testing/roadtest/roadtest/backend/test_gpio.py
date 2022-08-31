# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from unittest.mock import MagicMock

from roadtest.backend.gpio import Gpio, IrqType


def test_irq_low() -> None:
    m = MagicMock()
    gpio = Gpio(backend=m, pin=1)

    gpio.set_irq_type(IrqType.LEVEL_LOW)
    m.trigger_gpio_irq.assert_not_called()

    gpio.unmask()
    m.trigger_gpio_irq.assert_called_once_with(1)
    m.trigger_gpio_irq.reset_mock()

    gpio.set(True)
    gpio.unmask()
    m.trigger_gpio_irq.assert_not_called()


def test_irq_high() -> None:
    m = MagicMock()
    gpio = Gpio(backend=m, pin=2)

    gpio.set_irq_type(IrqType.LEVEL_HIGH)
    gpio.unmask()

    m.trigger_gpio_irq.assert_not_called()

    gpio.set(True)
    m.trigger_gpio_irq.assert_called_once_with(2)
    m.trigger_gpio_irq.reset_mock()

    gpio.set(False)
    gpio.unmask()
    m.trigger_gpio_irq.assert_not_called()


def test_irq_rising() -> None:
    m = MagicMock()
    gpio = Gpio(backend=m, pin=63)

    gpio.set_irq_type(IrqType.EDGE_RISING)
    gpio.set(False)
    gpio.set(True)

    m.trigger_gpio_irq.assert_not_called()
    gpio.unmask()
    m.trigger_gpio_irq.assert_called_once_with(63)
    m.trigger_gpio_irq.reset_mock()

    gpio.set(False)
    gpio.set(True)

    gpio.unmask()
    m.trigger_gpio_irq.assert_called_once()


def test_irq_falling() -> None:
    m = MagicMock()
    gpio = Gpio(backend=m, pin=0)

    gpio.set_irq_type(IrqType.EDGE_FALLING)
    gpio.unmask()
    gpio.set(False)
    gpio.set(True)
    m.trigger_gpio_irq.assert_not_called()

    gpio.set(False)
    m.trigger_gpio_irq.assert_called_once_with(0)
    m.trigger_gpio_irq.reset_mock()

    gpio.set(True)
    gpio.set(False)
    gpio.set(True)
    gpio.unmask()
    m.trigger_gpio_irq.assert_called_once()


def test_irq_both() -> None:
    m = MagicMock()
    gpio = Gpio(backend=m, pin=32)

    gpio.set_irq_type(IrqType.EDGE_BOTH)
    gpio.unmask()
    gpio.set(False)
    gpio.set(True)
    m.trigger_gpio_irq.assert_called_once_with(32)

    gpio.set(False)
    m.trigger_gpio_irq.assert_called_once_with(32)
    m.trigger_gpio_irq.reset_mock()

    gpio.set(True)
    gpio.unmask()
    m.trigger_gpio_irq.assert_called_once_with(32)
