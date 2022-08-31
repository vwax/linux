# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from typing import Any, Final, Iterator

import pytest

from roadtest.backend.i2c import SMBusModel
from roadtest.core.devicetree import DtFragment, I2CAddr
from roadtest.core.hardware import I2CHardware
from roadtest.support.sysfs import I2CDriver
from roadtest.tests.iio.iio import IIODevice

REG_RESULT: Final = 0x00
REG_CONFIGURATION: Final = 0x01
REG_LOW_LIMIT: Final = 0x02
REG_HIGH_LIMIT: Final = 0x03
REG_MANUFACTURER_ID: Final = 0x7E
REG_DEVICE_ID: Final = 0x7F

REG_CONFIGURATION_CRF: Final = 1 << 7


class OPT3001(SMBusModel):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(regbytes=2, byteorder="big", **kwargs)
        # Reset values from datasheet
        self.regs = {
            REG_RESULT: 0x0000,
            REG_CONFIGURATION: 0xC810,
            REG_LOW_LIMIT: 0xC000,
            REG_HIGH_LIMIT: 0xBFFF,
            REG_MANUFACTURER_ID: 0x5449,
            REG_DEVICE_ID: 0x3001,
        }

    def reg_read(self, addr: int) -> int:
        val = self.regs[addr]

        if addr == REG_CONFIGURATION:
            # Always indicate that the conversion is ready.  This is good
            # enough for our current purposes.
            val |= REG_CONFIGURATION_CRF

        return val

    def reg_write(self, addr: int, val: int) -> None:
        assert addr in self.regs
        self.regs[addr] = val


dts = DtFragment(
    src="""
&i2c {
light-sensor@$addr$ {
    compatible = "ti,opt3001";
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
    with I2CHardware(OPT3001) as hw:
        yield hw


@pytest.fixture(scope="module")
def dev() -> Iterator:
    with I2CDriver("opt3001").bind(dts.i2c["addr"]) as dev:
        yield IIODevice(dev.path)


@pytest.mark.parametrize(
    "regval,lux",
    [
        # Some values from datasheet, and 0
        (0b_0000_0000_0000_0000, 0),
        (0b_0000_0000_0000_0001, 0.01),
        (0b_0011_0100_0101_0110, 88.80),
        (0b_0111_1000_1001_1010, 2818.56),
    ],
)
def test_illuminance(
    hw: I2CHardware[OPT3001], dev: IIODevice, regval: int, lux: float
) -> None:
    hw.model.reg_write(REG_RESULT, regval)
    assert float(dev.in_illuminance_input) == lux
