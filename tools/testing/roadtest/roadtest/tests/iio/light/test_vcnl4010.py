# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import errno
import logging
from pathlib import Path
from typing import Any, Final, Optional

from roadtest.backend.i2c import SMBusModel
from roadtest.core.devicetree import DtFragment, DtVar
from roadtest.core.hardware import Hardware
from roadtest.core.modules import insmod, rmmod
from roadtest.core.suite import UMLTestCase
from roadtest.core.sysfs import (
    I2CDriver,
    read_float,
    read_int,
    read_str,
    write_int,
    write_str,
)
from roadtest.tests.iio import iio

logger = logging.getLogger(__name__)

REG_COMMAND: Final = 0x80
REG_PRODUCT_ID_REVISION: Final = 0x81
REG_PROXIMITY_RATE: Final = 0x82
REG_IR_LED_CURRENT: Final = 0x83
REG_ALS_PARAM: Final = 0x84
REG_ALS_RESULT_HIGH: Final = 0x85
REG_ALS_RESULT_LOW: Final = 0x86
REG_PROX_RESULT_HIGH: Final = 0x87
REG_PROX_RESULT_LOW: Final = 0x88
REG_INTERRUPT_CONTROL: Final = 0x89
REG_LOW_THRESHOLD_HIGH: Final = 0x8A
REG_LOW_THRESHOLD_LOW: Final = 0x8B
REG_HIGH_THRESHOLD_HIGH: Final = 0x8C
REG_HIGH_THRESHOLD_LOW: Final = 0x8D
REG_INTERRUPT_STATUS: Final = 0x8E

REG_COMMAND_ALS_DATA_RDY: Final = 1 << 6
REG_COMMAND_PROX_DATA_RDY: Final = 1 << 5


class VCNL4010(SMBusModel):
    def __init__(self, int: Optional[int] = None, **kwargs: Any) -> None:
        super().__init__(regbytes=1, **kwargs)
        self.int = int
        self._set_int(False)
        self.regs = {
            REG_COMMAND: 0b_1000_0000,
            REG_PRODUCT_ID_REVISION: 0x21,
            REG_PROXIMITY_RATE: 0x00,
            REG_IR_LED_CURRENT: 0x00,
            REG_ALS_PARAM: 0x00,
            REG_ALS_RESULT_HIGH: 0x00,
            REG_ALS_RESULT_LOW: 0x00,
            REG_PROX_RESULT_HIGH: 0x00,
            REG_PROX_RESULT_LOW: 0x00,
            REG_INTERRUPT_CONTROL: 0x00,
            REG_LOW_THRESHOLD_HIGH: 0x00,
            REG_LOW_THRESHOLD_LOW: 0x00,
            REG_HIGH_THRESHOLD_HIGH: 0x00,
            REG_HIGH_THRESHOLD_LOW: 0x00,
            REG_INTERRUPT_STATUS: 0x00,
        }

    def _set_int(self, active: int) -> None:
        # Active-low
        self.backend.gpio.set(self.int, not active)

    def _update_irq(self) -> None:
        selftimed_en = self.regs[REG_COMMAND] & (1 << 0)
        prox_en = self.regs[REG_COMMAND] & (1 << 1)
        prox_data_rdy = self.regs[REG_COMMAND] & REG_COMMAND_PROX_DATA_RDY
        int_prox_ready_en = self.regs[REG_INTERRUPT_CONTROL] & (1 << 3)

        logger.debug(
            f"{selftimed_en=:x} {prox_en=:x} {prox_data_rdy=:x} {int_prox_ready_en=:x}"
        )

        if selftimed_en and prox_en and prox_data_rdy and int_prox_ready_en:
            self.regs[REG_INTERRUPT_STATUS] |= 1 << 3

        low_threshold = (
            self.regs[REG_LOW_THRESHOLD_HIGH] << 8 | self.regs[REG_LOW_THRESHOLD_LOW]
        )
        high_threshold = (
            self.regs[REG_HIGH_THRESHOLD_HIGH] << 8 | self.regs[REG_HIGH_THRESHOLD_LOW]
        )
        proximity = (
            self.regs[REG_PROX_RESULT_HIGH] << 8 | self.regs[REG_PROX_RESULT_LOW]
        )
        int_thres_en = self.regs[REG_INTERRUPT_CONTROL] & (1 << 1)

        logger.debug(
            f"{low_threshold=:x} {high_threshold=:x} {proximity=:x} {int_thres_en=:x}"
        )

        if int_thres_en:
            if proximity < low_threshold:
                logger.debug("LOW")
                self.regs[REG_INTERRUPT_STATUS] |= 1 << 1
            if proximity > high_threshold:
                logger.debug("HIGH")
                self.regs[REG_INTERRUPT_STATUS] |= 1 << 0

        self._set_int(self.regs[REG_INTERRUPT_STATUS])

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
            rw = 0b_0001_1111
            val = (self.regs[addr] & ~rw) | (val & rw)
        elif addr == REG_INTERRUPT_STATUS:
            val = self.regs[addr] & ~(val & 0xF)

        self.regs[addr] = val
        self._update_irq()

    def inject(self, addr: int, val: int, mask: int = ~0) -> None:
        old = self.regs[addr] & ~mask
        new = old | (val & mask)
        self.regs[addr] = new
        self._update_irq()

    def set_bit(self, addr: int, val: int) -> None:
        self.inject(addr, val, val)


class TestVCNL4010(UMLTestCase):
    dts = DtFragment(
        src="""
#include <dt-bindings/interrupt-controller/irq.h>

&i2c {
    light-sensor@$addr$ {
        compatible = "vishay,vcnl4020";
        reg = <0x$addr$>;
        interrupt-parent = <&gpio>;
        interrupts = <$gpio$ IRQ_TYPE_EDGE_FALLING>;
    };
};
        """,
        variables={
            "addr": DtVar.I2C_ADDR,
            "gpio": DtVar.GPIO_PIN,
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
        self.hw.load_model(VCNL4010, int=self.dts["gpio"])

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
                self.hw.set_bit(REG_COMMAND, REG_COMMAND_ALS_DATA_RDY)

                self.assertEqual(read_int(luxfile), high << 8 | low)

    def test_lux_timeout(self) -> None:
        with self.driver.bind(self.dts["addr"]) as dev:
            with self.assertRaises(OSError) as cm:
                luxfile = dev.path / "iio:device0/in_illuminance_raw"
                read_str(luxfile)
            self.assertEqual(cm.exception.errno, errno.EIO)

    def test_proximity_thresh_rising(self) -> None:
        with self.driver.bind(self.dts["addr"]) as dev:
            high_thresh = (
                dev.path / "iio:device0/events/in_proximity_thresh_rising_value"
            )
            write_int(high_thresh, 0x1234)

            mock = self.hw.update_mock()
            mock.assert_last_reg_write(self, REG_HIGH_THRESHOLD_HIGH, 0x12)
            mock.assert_last_reg_write(self, REG_HIGH_THRESHOLD_LOW, 0x34)
            mock.reset_mock()

            self.assertEqual(read_int(high_thresh), 0x1234)

            with iio.IIOEventMonitor("/dev/iio:device0") as mon:
                en = dev.path / "iio:device0/events/in_proximity_thresh_either_en"
                write_int(en, 1)

                self.hw.inject(REG_PROX_RESULT_HIGH, 0x12)
                self.hw.inject(REG_PROX_RESULT_LOW, 0x35)
                self.hw.set_bit(REG_COMMAND, REG_COMMAND_PROX_DATA_RDY)
                self.hw.kick()

                self.assertEqual(read_int(en), 1)

                event = mon.read()
                self.assertEqual(event.type, iio.IIOChanType.IIO_PROXIMITY)

    def test_proximity_thresh_falling(self) -> None:
        with self.driver.bind(self.dts["addr"]) as dev:
            high_thresh = (
                dev.path / "iio:device0/events/in_proximity_thresh_falling_value"
            )
            write_int(high_thresh, 0x0ABC)

            mock = self.hw.update_mock()
            mock.assert_last_reg_write(self, REG_LOW_THRESHOLD_HIGH, 0x0A)
            mock.assert_last_reg_write(self, REG_LOW_THRESHOLD_LOW, 0xBC)
            mock.reset_mock()

            self.assertEqual(read_int(high_thresh), 0x0ABC)

            with iio.IIOEventMonitor("/dev/iio:device0") as mon:
                write_int(
                    dev.path / "iio:device0/events/in_proximity_thresh_either_en", 1
                )

                event = mon.read()
                self.assertEqual(event.type, iio.IIOChanType.IIO_PROXIMITY)

    def test_proximity_triggered(self) -> None:
        with self.driver.bind(self.dts["addr"]) as dev:
            data = [
                (0x00, 0x00, 0),
                (0x00, 0x01, 1),
                (0xF0, 0x02, 0xF002),
                (0xFF, 0xFF, 0xFFFF),
            ]

            trigger = read_str(Path("/sys/bus/iio/devices/trigger0/name"))

            write_int(dev.path / "iio:device0/buffer0/in_proximity_en", 1)
            write_str(dev.path / "iio:device0/trigger/current_trigger", trigger)

            with iio.IIOBuffer("/dev/iio:device0", bufidx=0) as buffer:
                write_int(dev.path / "iio:device0/buffer0/length", 128)
                write_int(dev.path / "iio:device0/buffer0/enable", 1)

                for low, high, expected in data:
                    self.hw.inject(REG_PROX_RESULT_HIGH, low)
                    self.hw.inject(REG_PROX_RESULT_LOW, high)
                    self.hw.set_bit(REG_COMMAND, REG_COMMAND_PROX_DATA_RDY)
                    self.hw.kick()

                    scanline = buffer.read("H")

                    val = scanline[0]
                    self.assertEqual(val, expected)
