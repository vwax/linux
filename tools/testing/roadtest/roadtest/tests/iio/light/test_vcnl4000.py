# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import errno
import logging
from typing import Any, Final, Iterator

import pytest

from roadtest.backend.i2c import SMBusModel
from roadtest.core.devicetree import DtFragment, I2CAddr
from roadtest.core.hardware import I2CHardware
from roadtest.support.sysfs import I2CDriver
from roadtest.tests.iio.iio import IIODevice

logger = logging.getLogger(__name__)

REG_COMMAND: Final = 0x80
REG_PRODUCT_ID_REVISION: Final = 0x81
REG_IR_LED_CURRENT: Final = 0x83
REG_ALS_PARAM: Final = 0x84
REG_ALS_RESULT_HIGH: Final = 0x85
REG_ALS_RESULT_LOW: Final = 0x86
REG_PROX_RESULT_HIGH: Final = 0x87
REG_PROX_RESULT_LOW: Final = 0x88
REG_PROX_SIGNAL_FREQ: Final = 0x89

REG_COMMAND_ALS_DATA_RDY: Final = 1 << 6
REG_COMMAND_PROX_DATA_RDY: Final = 1 << 5


class VCNL4000(SMBusModel):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(regbytes=1, **kwargs)
        self.regs = {
            REG_COMMAND: 0b_1000_0000,
            REG_PRODUCT_ID_REVISION: 0x11,
            # Register "without function in current version"
            0x82: 0x00,
            REG_IR_LED_CURRENT: 0x00,
            REG_ALS_PARAM: 0x00,
            REG_ALS_RESULT_HIGH: 0x00,
            REG_ALS_RESULT_LOW: 0x00,
            REG_PROX_RESULT_HIGH: 0x00,
            REG_PROX_RESULT_LOW: 0x00,
            REG_PROX_RESULT_LOW: 0x00,
        }

    def reg_read(self, addr: int) -> int:
        val = self.regs[addr]

        if addr in (REG_ALS_RESULT_HIGH, REG_ALS_RESULT_LOW):
            self.regs[REG_COMMAND] &= ~REG_COMMAND_ALS_DATA_RDY
        if addr in (REG_PROX_RESULT_HIGH, REG_PROX_RESULT_LOW):
            self.regs[REG_COMMAND] &= ~REG_COMMAND_PROX_DATA_RDY

        return val

    def reg_write(self, addr: int, val: int) -> None:
        assert addr in self.regs

        if addr == REG_COMMAND:
            rw = 0b_0001_1000
            val = (self.regs[addr] & ~rw) | (val & rw)

        self.regs[addr] = val

    def inject(self, addr: int, val: int, mask: int = ~0) -> None:
        old = self.regs[addr] & ~mask
        new = old | (val & mask)
        self.regs[addr] = new


dts = DtFragment(
    src="""
&i2c {
light-sensor@$addr$ {
    compatible = "vishay,vcnl4000";
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
    with I2CHardware(VCNL4000) as hw:
        yield hw


@pytest.fixture(scope="module")
def dev() -> Iterator:
    with I2CDriver("vcnl4000").bind(dts.i2c["addr"]) as dev:
        yield IIODevice(dev.path)


def test_scale(hw: I2CHardware[VCNL4000], dev: IIODevice) -> None:
    assert float(dev.in_illuminance_scale) == 0.25


@pytest.mark.parametrize(
    "high,low",
    [
        (0x00, 0x00),
        (0x12, 0x34),
        (0xFF, 0xFF),
    ],
)
def test_lux(hw: I2CHardware[VCNL4000], dev: IIODevice, high: int, low: int) -> None:
    hw.model.inject(REG_ALS_RESULT_HIGH, high)
    hw.model.inject(REG_ALS_RESULT_LOW, low)
    hw.model.inject(
        REG_COMMAND,
        val=REG_COMMAND_ALS_DATA_RDY,
        mask=REG_COMMAND_ALS_DATA_RDY,
    )

    assert int(dev.in_illuminance_raw) == high << 8 | low


def test_lux_timeout(hw: I2CHardware[VCNL4000], dev: IIODevice) -> None:
    with pytest.raises(OSError) as ex:
        dev.in_illuminance_raw
    assert ex.value.errno == errno.EIO
