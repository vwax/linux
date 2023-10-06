# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB
from typing import Iterator

import pytest

from roadtest.core.devicetree import DtFragment, GpioPin, NodeName
from roadtest.core.hardware import NoBusHardware
from roadtest.support.sysfs import PlatformDriver

dts = DtFragment(
    src="""
#include <dt-bindings/gpio/gpio.h>s
#include <dt-bindings/interrupt-controller/irq.h>

/ {
    $dev$ {
        compatible = "regulator-gpio";
        regulator-name = "foo";
        regulator-min-microvolt = <1800000>;
        regulator-max-microvolt = <2800000>;
        regulator-boot-on;

        gpios = <&gpio $state$ GPIO_ACTIVE_HIGH>;
        states = <2800000 1>, <1800000 0>;

        enable-gpios = <&gpio $enable$ GPIO_ACTIVE_HIGH>;
        enable-active-high;
    };
};
    """,
    name={"dev": NodeName()},
    gpio={"enable": GpioPin(), "state": GpioPin()},
)


@pytest.fixture(scope="module")
def hw() -> Iterator:
    with NoBusHardware() as hw:
        yield hw


# This is for testing roadtest's gpio support, we just use gpio-regulator
# because it is convenient.
def test_gpio_set_value(hw: NoBusHardware) -> None:
    with PlatformDriver("gpio-regulator").bind(dts.name["dev"]):
        enablepin = dts.gpio["enable"]

        mock = hw.update_mock()
        mock.gpio_set_value.assert_called_with(enablepin.val, 1)
