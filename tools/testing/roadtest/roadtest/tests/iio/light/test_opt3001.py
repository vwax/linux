# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from typing import Any, Final

from roadtest.backend.i2c import SMBusModel
from roadtest.core.devicetree import DtFragment, DtVar
from roadtest.core.hardware import Hardware
from roadtest.core.modules import insmod, rmmod
from roadtest.core.suite import UMLTestCase
from roadtest.core.sysfs import I2CDriver, read_float

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


class TestOPT3001(UMLTestCase):
    dts = DtFragment(
        src="""
&i2c {
    light-sensor@$addr$ {
        compatible = "ti,opt3001";
        reg = <0x$addr$>;
    };
};
        """,
        variables={
            "addr": DtVar.I2C_ADDR,
        },
    )

    @classmethod
    def setUpClass(cls) -> None:
        insmod("opt3001")

    @classmethod
    def tearDownClass(cls) -> None:
        rmmod("opt3001")

    def setUp(self) -> None:
        self.driver = I2CDriver("opt3001")
        self.hw = Hardware("i2c")
        self.hw.load_model(OPT3001)

    def tearDown(self) -> None:
        self.hw.close()

    def test_illuminance(self) -> None:
        data = [
            # Some values from datasheet, and 0
            (0b_0000_0000_0000_0000, 0),
            (0b_0000_0000_0000_0001, 0.01),
            (0b_0011_0100_0101_0110, 88.80),
            (0b_0111_1000_1001_1010, 2818.56),
        ]
        with self.driver.bind(self.dts["addr"]) as dev:
            luxfile = dev.path / "iio:device0/in_illuminance_input"

            for regval, lux in data:
                self.hw.reg_write(REG_RESULT, regval)
                self.assertEqual(read_float(luxfile), lux)
