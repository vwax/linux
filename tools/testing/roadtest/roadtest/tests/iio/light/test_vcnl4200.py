# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import logging

# from pathlib import Path
from typing import Any, Iterator

import pytest

from roadtest.backend.i2c import SMBusModel
from roadtest.core.devicetree import DtFragment, I2CAddr
from roadtest.core.hardware import Hardware, I2CHardware
from roadtest.support.sysfs import I2CDriver
from roadtest.tests.iio.iio import IIODevice

logger = logging.getLogger(__name__)


class VCNL4200(SMBusModel):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(regbytes=2, byteorder="little", **kwargs)
        self.regs = {
            0x00: 0x0101,
            0x01: 0x0000,
            0x02: 0x0000,
            0x03: 0x0001,
            0x04: 0x0000,
            0x05: 0x0000,
            0x06: 0x0000,
            0x07: 0x0000,
            0x08: 0x0000,
            0x09: 0x0000,
            0x0A: 0x0000,
            0x0D: 0x0000,
            0x0E: 0x1058,
        }

    def reg_read(self, addr: int) -> int:
        return self.regs[addr]

    def reg_write(self, addr: int, val: int) -> None:
        assert addr in self.regs
        self.regs[addr] = val


dts = DtFragment(
    src="""
&i2c {
    light-sensor@$addr$ {
        compatible = "vishay,vcnl4200";
        reg = <0x$addr$>;
    };
};
    """,
    i2c={
        "addr": I2CAddr(),
    },
)


@pytest.fixture(scope="module", autouse=True)
def hw() -> Iterator:
    with I2CHardware(VCNL4200) as hw:
        yield hw


@pytest.fixture(scope="module")
def dev() -> Iterator:
    with I2CDriver("vcnl4000").bind(dts.i2c["addr"]) as dev:
        yield IIODevice(dev.path)


def test_illuminance_scale(dev: IIODevice) -> None:
    assert float(dev.in_illuminance_scale) == 0.024


@pytest.mark.parametrize("data", [0x0000, 0x1234, 0xFFFF])
def test_illuminance(hw: Hardware[VCNL4200], dev: IIODevice, data: int) -> None:
    hw.model.regs[0x09] = data
    assert int(dev.in_illuminance_raw) == data


@pytest.mark.parametrize("data", [0x0000, 0x1234, 0xFFFF])
def test_proximity(hw: Hardware[VCNL4200], dev: IIODevice, data: int) -> None:
    hw.model.regs[0x08] = data
    assert int(dev.in_proximity_raw) == data
