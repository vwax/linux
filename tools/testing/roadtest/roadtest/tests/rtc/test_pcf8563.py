# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import errno
import logging
from typing import Any, Final, Optional

from roadtest.backend.i2c import I2CModel
from roadtest.core.devicetree import DtFragment, DtVar
from roadtest.core.hardware import Hardware
from roadtest.core.modules import insmod
from roadtest.core.suite import UMLTestCase
from roadtest.core.sysfs import I2CDriver

from . import rtc

logger = logging.getLogger(__name__)

REG_CONTROL_STATUS_1: Final = 0x00
REG_CONTROL_STATUS_2: Final = 0x01
REG_VL_SECONDS: Final = 0x02
REG_VL_MINUTES: Final = 0x03
REG_VL_HOURS: Final = 0x04
REG_VL_DAYS: Final = 0x05
REG_VL_WEEKDAYS: Final = 0x06
REG_VL_CENTURY_MONTHS: Final = 0x07
REG_VL_YEARS: Final = 0x08
REG_VL_MINUTE_ALARM: Final = 0x09
REG_VL_HOUR_ALARM: Final = 0x0A
REG_VL_DAY_ALARM: Final = 0x0B
REG_VL_WEEKDAY_ALARM: Final = 0x0C
REG_CLKOUT_CONTROL: Final = 0x0D
REG_TIMER_CONTROL: Final = 0x0E
REG_TIMER: Final = 0x0F

REG_CONTROL_STATUS_2_AIE: Final = 1 << 1
REG_CONTROL_STATUS_2_AF: Final = 1 << 3

REG_VL_CENTURY_MONTHS_C: Final = 1 << 7

REG_VL_ALARM_AE: Final = 1 << 7


class PCF8563(I2CModel):
    def __init__(self, int: Optional[int] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.int = int
        self._set_int(False)

        self.reg_addr = 0
        # Reset values from Table 27 in datasheet, with X and - bits set to 0
        self.regs = {
            REG_CONTROL_STATUS_1: 0b_0000_1000,
            REG_CONTROL_STATUS_2: 0b_0000_0000,
            REG_VL_SECONDS: 0b_1000_0000,
            REG_VL_MINUTES: 0b_0000_0000,
            REG_VL_HOURS: 0b_0000_0000,
            REG_VL_DAYS: 0b_0000_0000,
            REG_VL_WEEKDAYS: 0b_0000_0000,
            REG_VL_CENTURY_MONTHS: 0b_0000_0000,
            REG_VL_YEARS: 0b_0000_0000,
            REG_VL_MINUTE_ALARM: 0b_1000_0000,
            REG_VL_HOUR_ALARM: 0b_1000_0000,
            REG_VL_DAY_ALARM: 0b_1000_0000,
            REG_VL_WEEKDAY_ALARM: 0b_1000_0000,
            REG_CLKOUT_CONTROL: 0b_1000_0000,
            REG_TIMER_CONTROL: 0b_0000_0011,
            REG_TIMER: 0b_0000_0000,
        }

    def _set_int(self, active: int) -> None:
        # Active-low
        self.backend.gpio.set(self.int, not active)

    def _check_alarm(self, addr: int) -> None:
        alarmregs = [
            REG_VL_MINUTE_ALARM,
            REG_VL_HOUR_ALARM,
            REG_VL_DAY_ALARM,
            REG_VL_WEEKDAY_ALARM,
        ]
        timeregs = [
            REG_VL_MINUTES,
            REG_VL_HOURS,
            REG_VL_DAYS,
            REG_VL_WEEKDAYS,
        ]

        if addr not in alarmregs + timeregs:
            return

        af = all(
            self.regs[a] == self.regs[b]
            for a, b in zip(alarmregs, timeregs)
            if not self.regs[a] & REG_VL_ALARM_AE
        )
        self.reg_write(REG_CONTROL_STATUS_2, self.regs[REG_CONTROL_STATUS_2] | af << 3)

    def _update_irq(self) -> None:
        aie = self.regs[REG_CONTROL_STATUS_2] & REG_CONTROL_STATUS_2_AIE
        af = self.regs[REG_CONTROL_STATUS_2] & REG_CONTROL_STATUS_2_AF

        logger.debug(f"{aie=} {af=}")
        self._set_int(aie and af)

    def reg_read(self, addr: int) -> int:
        val = self.regs[addr]
        return val

    def reg_write(self, addr: int, val: int) -> None:
        assert addr in self.regs
        self.regs[addr] = val
        logger.debug(f"{addr=:x} {val=:x}")
        self._check_alarm(addr)
        self._update_irq()

    def read(self, len: int) -> bytes:
        data = bytearray(len)

        for i in range(len):
            data[i] = self.reg_read(self.reg_addr)
            self.reg_addr = self.reg_addr + 1

        return bytes(data)

    def write(self, data: bytes) -> None:
        self.reg_addr = data[0]

        for i, byte in enumerate(data[1:]):
            addr = self.reg_addr + i
            self.backend.mock.reg_write(addr, byte)
            self.reg_write(addr, byte)


class TestPCF8563(UMLTestCase):
    dts = DtFragment(
        src="""
#include <dt-bindings/interrupt-controller/irq.h>

&i2c {
    rtc@$addr$ {
        compatible = "nxp,pcf8563";
        reg = <0x$addr$>;
    };

    rtc@$irqaddr$ {
        compatible = "nxp,pcf8563";
        reg = <0x$irqaddr$>;
        interrupt-parent = <&gpio>;
        interrupts = <$gpio$ IRQ_TYPE_LEVEL_LOW>;
    };
};
        """,
        variables={
            "addr": DtVar.I2C_ADDR,
            "irqaddr": DtVar.I2C_ADDR,
            "gpio": DtVar.GPIO_PIN,
        },
    )

    @classmethod
    def setUpClass(cls) -> None:
        insmod("rtc-pcf8563")

    @classmethod
    def tearDownClass(cls) -> None:
        # Can't rmmod since alarmtimer holds permanent reference
        pass

    def setUp(self) -> None:
        self.driver = I2CDriver("rtc-pcf8563")
        self.hw = Hardware("i2c")
        self.hw.load_model(PCF8563, int=self.dts["gpio"])

    def tearDown(self) -> None:
        self.hw.close()

    def test_read_time_invalid(self) -> None:
        addr = self.dts["addr"]
        with self.driver.bind(addr) as dev, rtc.RTC(dev.path) as rtcdev:
            self.assertEqual(rtcdev.read_vl(), rtc.RTC_VL_DATA_INVALID)

            with self.assertRaises(OSError) as cm:
                rtcdev.read_time()
            self.assertEqual(cm.exception.errno, errno.EINVAL)

    def test_no_alarm_support(self) -> None:
        addr = self.dts["addr"]
        with self.driver.bind(addr) as dev, rtc.RTC(dev.path) as rtcdev:
            # Make sure the times are valid so we don't get -EINVAL due to
            # that.
            tm = rtc.RTCTime(
                tm_sec=10,
                tm_min=1,
                tm_hour=1,
                tm_mday=1,
                tm_mon=0,
                tm_year=121,
                tm_wday=0,
                tm_yday=0,
                tm_isdst=0,
            )
            rtcdev.set_time(tm)

            alarmtm = tm._replace(tm_sec=0, tm_min=2)
            with self.assertRaises(OSError) as cm:
                rtcdev.set_wake_alarm(True, alarmtm)
            self.assertEqual(cm.exception.errno, errno.EINVAL)

    def test_alarm(self) -> None:
        addr = self.dts["irqaddr"]
        with self.driver.bind(addr) as dev, rtc.RTC(dev.path) as rtcdev:
            tm = rtc.RTCTime(
                tm_sec=10,
                tm_min=1,
                tm_hour=1,
                tm_mday=1,
                tm_mon=0,
                tm_year=121,
                tm_wday=5,
                tm_yday=0,
                tm_isdst=0,
            )
            rtcdev.set_time(tm)

            alarmtm = tm._replace(tm_sec=0, tm_min=2)
            rtcdev.set_wake_alarm(True, alarmtm)

            mock = self.hw.update_mock()
            mock.assert_last_reg_write(self, REG_VL_MINUTE_ALARM, 0x02)
            mock.assert_last_reg_write(self, REG_VL_HOUR_ALARM, 0x01)
            mock.assert_last_reg_write(self, REG_VL_DAY_ALARM, 0x01)
            mock.assert_last_reg_write(self, REG_VL_WEEKDAY_ALARM, 5)
            mock.assert_last_reg_write(
                self, REG_CONTROL_STATUS_2, REG_CONTROL_STATUS_2_AIE
            )
            mock.reset_mock()

            self.hw.reg_write(REG_VL_MINUTES, 0x02)
            self.hw.kick()

            # This waits for the interrupt
            self.assertEqual(rtcdev.read() & 0xFF, rtc.RTC_IRQF | rtc.RTC_AF)

            alarmtm = tm._replace(tm_sec=0, tm_min=3)
            rtcdev.set_wake_alarm(False, alarmtm)

            mock = self.hw.update_mock()
            mock.assert_last_reg_write(self, REG_CONTROL_STATUS_2, 0)

    def test_read_time_valid(self) -> None:
        self.hw.reg_write(REG_VL_SECONDS, 0x37)
        self.hw.reg_write(REG_VL_MINUTES, 0x10)
        self.hw.reg_write(REG_VL_HOURS, 0x11)
        self.hw.reg_write(REG_VL_DAYS, 0x25)
        self.hw.reg_write(REG_VL_WEEKDAYS, 0x00)
        self.hw.reg_write(REG_VL_CENTURY_MONTHS, REG_VL_CENTURY_MONTHS_C | 0x12)
        self.hw.reg_write(REG_VL_YEARS, 0x21)

        addr = self.dts["addr"]
        with self.driver.bind(addr) as dev, rtc.RTC(dev.path) as rtcdev:
            tm = rtcdev.read_time()
            self.assertEqual(
                tm,
                rtc.RTCTime(
                    tm_sec=37,
                    tm_min=10,
                    tm_hour=11,
                    tm_mday=25,
                    tm_mon=11,
                    tm_year=121,
                    tm_wday=0,
                    tm_yday=0,
                    tm_isdst=0,
                ),
            )

    def test_set_time_after_invalid(self) -> None:
        addr = self.dts["addr"]
        with self.driver.bind(addr) as dev, rtc.RTC(dev.path) as rtcdev:
            self.assertEqual(rtcdev.read_vl(), rtc.RTC_VL_DATA_INVALID)

            tm = rtc.RTCTime(
                tm_sec=37,
                tm_min=10,
                tm_hour=11,
                tm_mday=25,
                tm_mon=11,
                tm_year=121,
                tm_wday=0,
                tm_yday=0,
                tm_isdst=0,
            )

            rtcdev.set_time(tm)
            tm2 = rtcdev.read_time()
            self.assertEqual(tm, tm2)

            mock = self.hw.update_mock()
            mock.assert_reg_write_once(self, REG_VL_SECONDS, 0x37)
            mock.assert_reg_write_once(self, REG_VL_MINUTES, 0x10)
            mock.assert_reg_write_once(self, REG_VL_HOURS, 0x11)
            mock.assert_reg_write_once(self, REG_VL_DAYS, 0x25)
            mock.assert_reg_write_once(self, REG_VL_WEEKDAYS, 0x00)
            # The driver uses the wrong polarity of the Century bit
            # if the time was invalid.  This probably doesn't matter(?).
            mock.assert_reg_write_once(self, REG_VL_CENTURY_MONTHS, 0 << 7 | 0x12)
            mock.assert_reg_write_once(self, REG_VL_YEARS, 0x21)

            self.assertEqual(rtcdev.read_vl(), 0)

    def test_set_time_after_valid(self) -> None:
        self.hw.reg_write(REG_VL_SECONDS, 0x37)
        self.hw.reg_write(REG_VL_MINUTES, 0x10)
        self.hw.reg_write(REG_VL_HOURS, 0x11)
        self.hw.reg_write(REG_VL_DAYS, 0x25)
        self.hw.reg_write(REG_VL_WEEKDAYS, 0x00)
        self.hw.reg_write(REG_VL_CENTURY_MONTHS, REG_VL_CENTURY_MONTHS_C | 0x12)
        self.hw.reg_write(REG_VL_YEARS, 0x21)

        addr = self.dts["addr"]
        with self.driver.bind(addr) as dev, rtc.RTC(dev.path) as rtcdev:
            tm = rtc.RTCTime(
                tm_sec=37,
                tm_min=10,
                tm_hour=11,
                tm_mday=25,
                tm_mon=11,
                tm_year=121,
                tm_wday=0,
                tm_yday=0,
                tm_isdst=0,
            )

            rtcdev.set_time(tm)
            tm2 = rtcdev.read_time()
            self.assertEqual(tm, tm2)

            mock = self.hw.update_mock()
            mock.assert_reg_write_once(self, REG_VL_SECONDS, 0x37)
            mock.assert_reg_write_once(self, REG_VL_MINUTES, 0x10)
            mock.assert_reg_write_once(self, REG_VL_HOURS, 0x11)
            mock.assert_reg_write_once(self, REG_VL_DAYS, 0x25)
            mock.assert_reg_write_once(self, REG_VL_WEEKDAYS, 0x00)
            mock.assert_reg_write_once(
                self, REG_VL_CENTURY_MONTHS, REG_VL_CENTURY_MONTHS_C | 0x12
            )
            mock.assert_reg_write_once(self, REG_VL_YEARS, 0x21)
