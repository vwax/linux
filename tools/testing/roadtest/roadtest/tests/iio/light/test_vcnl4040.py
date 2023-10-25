# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import logging
from typing import Any, Final, Iterator

import pytest

from roadtest.backend.i2c import SMBusModel
from roadtest.core.devicetree import DtFragment, I2CAddr
from roadtest.core.hardware import I2CHardware
from roadtest.support.sysfs import I2CDriver
from roadtest.tests.iio.iio import IIODevice

logger = logging.getLogger(__name__)

ALS_CONF: Final = 0x00
ALS_CONF_ALS_SD: Final = 0x01
PS_CONF1: Final = 0x03
PS_CONF1_PS_SD: Final = 0x01
PS_DATA: Final = 0x08
ALS_DATA: Final = 0x09


class VCNL4040(SMBusModel):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(regbytes=2, byteorder="little", **kwargs)
        self.regs = {
            0x00: 0x0001,
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
            0x0A: 0x0000,
            0x0B: 0x0000,
            0x0C: 0x0186,
            # The driver reads this register which is undefined for
            # VCNL4040.  Perhaps the driver should be fixed instead
            # of having this here?
            0x0E: 0x0000,
        }

    def reg_read(self, addr: int) -> int:
        return self.regs[addr]

    def reg_write(self, addr: int, val: int) -> None:
        assert addr in self.regs
        self.regs[addr] = val

    def inject(self, addr: int, val: int) -> None:
        self.regs[addr] = val


dts = DtFragment(
    src="""
&i2c {
light-sensor@$addr$ {
    compatible = "vishay,vcnl4040";
    reg = <0x$addr$>;
};
};
    """,
    i2c={
        "addr": I2CAddr(),
    },
)


@pytest.fixture(scope="module")
def hw() -> Iterator:
    with I2CHardware(VCNL4040) as hw:
        yield hw


@pytest.fixture(scope="module")
def dev() -> Iterator:
    with I2CDriver("vcnl4000").bind(dts.i2c["addr"]) as dev:
        yield IIODevice(dev.path)


def test_illuminance_scale(hw: I2CHardware[VCNL4040], dev: IIODevice) -> None:
    assert float(dev.in_illuminance_scale) == 0.10


@pytest.mark.parametrize("data", [0x0000, 0x1234, 0xFFFF])
def test_illuminance(hw: I2CHardware[VCNL4040], dev: IIODevice, data: int) -> None:
    hw.model.reg_write(ALS_DATA, data)
    assert int(dev.in_illuminance_raw) == data


@pytest.mark.parametrize("data", [0x0000, 0x1234, 0xFFFF])
def test_proximity(hw: I2CHardware[VCNL4040], dev: IIODevice, data: int) -> None:
    hw.model.reg_write(PS_DATA, data)
    assert int(dev.in_proximity_raw) == data
