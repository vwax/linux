# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import logging
from typing import Any

from roadtest.backend.i2c import SMBusModel
from roadtest.core.devicetree import DtFragment, DtVar
from roadtest.core.hardware import Hardware
from roadtest.core.modules import insmod, rmmod
from roadtest.core.suite import UMLTestCase
from roadtest.core.sysfs import I2CDriver, read_float, read_int

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


class TestVCNL4200(UMLTestCase):
    dts = DtFragment(
        src="""
&i2c {
    light-sensor@$addr$ {
        compatible = "vishay,vcnl4200";
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
        insmod("vcnl4000")

    @classmethod
    def tearDownClass(cls) -> None:
        rmmod("vcnl4000")

    def setUp(self) -> None:
        self.driver = I2CDriver("vcnl4000")
        self.hw = Hardware("i2c")
        self.hw.load_model(VCNL4200)

    def tearDown(self) -> None:
        self.hw.close()

    def test_illuminance_scale(self) -> None:
        with self.driver.bind(self.dts["addr"]) as dev:
            scalefile = dev.path / "iio:device0/in_illuminance_scale"
            self.assertEqual(read_float(scalefile), 0.024)

    def test_illuminance(self) -> None:
        with self.driver.bind(self.dts["addr"]) as dev:
            luxfile = dev.path / "iio:device0/in_illuminance_raw"

            data = [0x0000, 0x1234, 0xFFFF]
            for regval in data:
                self.hw.reg_write(0x09, regval)
                self.assertEqual(read_int(luxfile), regval)

    def test_proximity(self) -> None:
        with self.driver.bind(self.dts["addr"]) as dev:
            rawfile = dev.path / "iio:device0/in_proximity_raw"

            data = [0x0000, 0x1234, 0xFFFF]
            for regval in data:
                self.hw.reg_write(0x08, regval)
                self.assertEqual(read_int(rawfile), regval)
