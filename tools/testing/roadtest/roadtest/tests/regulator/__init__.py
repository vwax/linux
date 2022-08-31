# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import contextlib
import random
from pathlib import Path
from typing import Callable, Iterator, Tuple, Type

from roadtest.backend.i2c import I2CModel
from roadtest.core.devicetree import DtFragment
from roadtest.core.hardware import Hardware, HwMock, I2CHardware
from roadtest.support.sysfs import (
    I2CDriver,
    PlatformDriver,
    read_int,
    read_str,
    write_int,
    write_str,
)


class Regulator:
    def __init__(self, path: Path) -> None:
        self.path = path

    @property
    def microvolts(self) -> int:
        return read_int(self.path / "microvolts")

    @property
    def name(self) -> str:
        return read_str(self.path / "name")

    @property
    def state(self) -> str:
        return read_str(self.path / "state")


class VirtualConsumer:
    def __init__(self, path: Path) -> None:
        self.path = path

    @property
    def max_microvolts(self) -> int:
        return read_int(self.path / "max_microvolts")

    @max_microvolts.setter
    def max_microvolts(self, value: int) -> None:
        write_int(self.path / "max_microvolts", value)

    @property
    def min_microvolts(self) -> int:
        return read_int(self.path / "min_microvolts")

    @min_microvolts.setter
    def min_microvolts(self, value: int) -> None:
        write_int(self.path / "min_microvolts", value)

    @property
    def mode(self) -> str:
        return read_str(self.path / "mode")

    @mode.setter
    def mode(self, value: str) -> None:
        write_str(self.path / "mode", value)

    def set_voltage(self, microvolts: int) -> None:
        self.min_microvolts = microvolts
        self.max_microvolts = microvolts


@contextlib.contextmanager
def bind(
    dts: DtFragment, model: Type[I2CModel], driver: str, name: str
) -> Iterator[Tuple[Hardware, Iterator[Regulator], VirtualConsumer]]:
    with (
        I2CHardware(model) as hw,
        I2CDriver(driver).bind(dts.i2c[name]) as dev,
        PlatformDriver("reg-virt-consumer").bind(dts.name[f"{name}-consumer"]) as cdev,
    ):
        yield (
            hw,
            (Regulator(p) for p in dev.path.glob("regulator/regulator*/")),
            VirtualConsumer(cdev.path),
        )


def voltage_test(
    hw: Hardware,
    reg: Regulator,
    consumer: VirtualConsumer,
    ranges: list,
    *,
    assert_enable: Callable[[HwMock], None],
    assert_disable: Callable[[HwMock], None],
    assert_voltage: Callable[[HwMock, int], None],
) -> None:
    first = True
    for range in ranges:
        consumer.max_microvolts = range[-1]

        previous = -1
        for voltage in [range[0], range[-1], random.choice(range)]:
            if previous == voltage:
                # Can't assert register writes for voltage changes
                # if the voltage is not changed
                continue

            consumer.min_microvolts = voltage

            mock = hw.update_mock()
            assert reg.microvolts == voltage
            assert_voltage(mock, voltage)

            if first:
                assert reg.state == "enabled"
                assert_enable(mock)
                first = False

            previous = voltage

    consumer.min_microvolts = 0
    assert reg.state == "disabled"
    assert_disable(hw.update_mock())
