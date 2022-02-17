# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import errno
import logging
from typing import Any, Final

from roadtest.backend.i2c import SMBusModel
from roadtest.core.devicetree import DtFragment, DtVar
from roadtest.core.hardware import Hardware
from roadtest.core.modules import insmod, rmmod
from roadtest.core.suite import UMLTestCase
from roadtest.core.sysfs import I2CDriver, read_float, read_int, read_str

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


class TestVCNL4000(UMLTestCase):
    dts = DtFragment(
        src="""
&i2c {
    light-sensor@$addr$ {
        compatible = "vishay,vcnl4000";
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
        self.hw.load_model(VCNL4000)

    def tearDown(self) -> None:
        self.hw.close()

    def test_lux(self) -> None:
        with self.driver.bind(self.dts["addr"]) as dev:
            scale = read_float(dev.path / "iio:device0/in_illuminance_scale")
            self.assertEqual(scale, 0.25)

            data = [
                (0x00, 0x00),
                (0x12, 0x34),
                (0xFF, 0xFF),
            ]
            luxfile = dev.path / "iio:device0/in_illuminance_raw"
            for high, low in data:
                self.hw.inject(REG_ALS_RESULT_HIGH, high)
                self.hw.inject(REG_ALS_RESULT_LOW, low)
                self.hw.inject(
                    REG_COMMAND,
                    val=REG_COMMAND_ALS_DATA_RDY,
                    mask=REG_COMMAND_ALS_DATA_RDY,
                )

                self.assertEqual(read_int(luxfile), high << 8 | low)

    def test_lux_timeout(self) -> None:
        with self.driver.bind(self.dts["addr"]) as dev:
            # self.hw.set_never_ready(True)
            with self.assertRaises(OSError) as cm:
                luxfile = dev.path / "iio:device0/in_illuminance_raw"
                read_str(luxfile)
            self.assertEqual(cm.exception.errno, errno.EIO)
