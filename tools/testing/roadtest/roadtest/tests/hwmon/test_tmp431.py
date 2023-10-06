# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB
from typing import Any, Final, Iterator

import pytest

from roadtest.backend.i2c import SMBusModel
from roadtest.core.devicetree import DtFragment, I2CAddr
from roadtest.core.hardware import I2CHardware
from roadtest.support.sysfs import I2CDriver

REG_STATUS: Final = 0x02
REG_CFG_1_READ: Final = 0x03
REG_CFG_1_WRITE: Final = 0x09
REG_CONV_RATE_READ: Final = 0x04
REG_CONV_RATE_WRITE: Final = 0x0A
REG_N_FACTOR: Final = 0x18
REG_BETA_RANGE: Final = 0x25
REG_SOFT_RESET: Final = 0xFC
REG_DEVICE_ID: Final = 0xFD
REG_MANUFACTOR_ID: Final = 0xFE

REG_CFG_EXTENDED_RANGE_MASK: Final = 1 << 2


class TMP431(SMBusModel):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(regbytes=1, **kwargs)
        self.regs = {
            REG_STATUS: 0x80,
            REG_CFG_1_READ: 0x00,
            REG_CFG_1_WRITE: 0xFF,
            REG_CONV_RATE_READ: 0x07,
            REG_CONV_RATE_WRITE: 0xFF,
            REG_N_FACTOR: 0x00,
            REG_BETA_RANGE: 0x08,
            REG_DEVICE_ID: 0x31,
            REG_MANUFACTOR_ID: 0x55,
        }

    def reg_read(self, addr: int) -> int:
        val = self.regs[addr]
        return val

    def reg_write(self, addr: int, val: int) -> None:
        if addr in (REG_CFG_1_WRITE, REG_CONV_RATE_WRITE):
            self.regs[addr - 6] = val
        self.regs[addr] = val


dts = DtFragment(
    src="""
&i2c {
    tmp1@$default$ {
        reg = <0x$default$>;
        compatible = "ti,tmp431";
    };
};

&i2c {
    tmp2@$advanced$ {
        reg = <0x$advanced$>;
        compatible = "ti,tmp431";
        ti,extended-range-enable;
        ti,n-factor = <0x3b>;
        ti,beta-compensation = <0x7>;
    };
};
    """,
    i2c={
        "default": I2CAddr(),
        "advanced": I2CAddr(),
    },
)


@pytest.fixture(scope="module")
def hw() -> Iterator:
    with I2CHardware(TMP431) as hw:
        yield hw


def test_default(hw: I2CHardware[TMP431]) -> None:
    with I2CDriver("tmp401").bind(dts.i2c["default"]):
        pass


def test_advanced(hw: I2CHardware[TMP431]) -> None:
    with I2CDriver("tmp401").bind(dts.i2c["advanced"]):
        mock = hw.update_mock()
        mock.assert_last_reg_set_mask(REG_CFG_1_WRITE, REG_CFG_EXTENDED_RANGE_MASK)
        mock.assert_reg_write_once(REG_N_FACTOR, 0x3B)
        mock.assert_last_reg_set_mask(REG_BETA_RANGE, 0x7)
