# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import contextlib
import fcntl
import struct
import typing
from pathlib import Path
from typing import Any, cast

RTC_RD_TIME = 0x80247009
RTC_SET_TIME = 0x4024700A
RTC_WKALM_SET = 0x4028700F
RTC_VL_READ = 0x80047013

RTC_IRQF = 0x80
RTC_AF = 0x20

RTC_VL_DATA_INVALID = 1 << 0


class RTCTime(typing.NamedTuple):
    tm_sec: int
    tm_min: int
    tm_hour: int
    tm_mday: int
    tm_mon: int
    tm_year: int
    tm_wday: int
    tm_yday: int
    tm_isdst: int


class RTC(contextlib.AbstractContextManager):
    def __init__(self, devpath: Path) -> None:
        rtc = next(devpath.glob("rtc/rtc*")).name
        self.filename = f"/dev/{rtc}"

    def __enter__(self) -> "RTC":
        self.file = open(self.filename, "rb")
        return self

    def __exit__(self, *_: Any) -> None:
        self.file.close()

    def read_time(self) -> RTCTime:
        s = struct.Struct("9i")
        buf = bytearray(s.size)
        fcntl.ioctl(self.file.fileno(), RTC_RD_TIME, buf)
        return RTCTime._make(s.unpack(buf))

    def set_time(self, tm: RTCTime) -> int:
        s = struct.Struct("9i")
        buf = bytearray(s.size)
        s.pack_into(buf, 0, *tm)
        return fcntl.ioctl(self.file.fileno(), RTC_SET_TIME, buf)

    def set_wake_alarm(self, enabled: bool, time: RTCTime) -> int:
        s = struct.Struct("2B9i")
        buf = bytearray(s.size)
        s.pack_into(buf, 0, enabled, False, *time)
        return fcntl.ioctl(self.file.fileno(), RTC_WKALM_SET, buf)

    def read(self) -> int:
        s = struct.Struct("L")
        buf = self.file.read(s.size)
        return cast(int, s.unpack(buf)[0])

    def read_vl(self) -> int:
        s = struct.Struct("I")
        buf = bytearray(s.size)
        fcntl.ioctl(self.file.fileno(), RTC_VL_READ, buf)
        return cast(int, s.unpack(buf)[0])
