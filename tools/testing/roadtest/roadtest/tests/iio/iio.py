# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import contextlib
import enum
import fcntl
import struct
from dataclasses import dataclass, field
from typing import Any

IIO_GET_EVENT_FD_IOCTL = 0x80046990
IIO_BUFFER_GET_FD_IOCTL = 0xC0046991


class IIOChanType(enum.IntEnum):
    IIO_VOLTAGE = 0
    IIO_CURRENT = 1
    IIO_POWER = 2
    IIO_ACCEL = 3
    IIO_ANGL_VEL = 4
    IIO_MAGN = 5
    IIO_LIGHT = 6
    IIO_INTENSITY = 7
    IIO_PROXIMITY = 8
    IIO_TEMP = 9
    IIO_INCLI = 10
    IIO_ROT = 11
    IIO_ANGL = 12
    IIO_TIMESTAMP = 13
    IIO_CAPACITANCE = 14
    IIO_ALTVOLTAGE = 15
    IIO_CCT = 16
    IIO_PRESSURE = 17
    IIO_HUMIDITYRELATIVE = 18
    IIO_ACTIVITY = 19
    IIO_STEPS = 20
    IIO_ENERGY = 21
    IIO_DISTANCE = 22
    IIO_VELOCITY = 23
    IIO_CONCENTRATION = 24
    IIO_RESISTANCE = 25
    IIO_PH = 26
    IIO_UVINDEX = 27
    IIO_ELECTRICALCONDUCTIVITY = 28
    IIO_COUNT = 29
    IIO_INDEX = 30
    IIO_GRAVITY = 31
    IIO_POSITIONRELATIVE = 32
    IIO_PHASE = 33
    IIO_MASSCONCENTRATION = 34


@dataclass
class IIOEvent:
    id: int
    timestamp: int
    type: IIOChanType = field(init=False)

    def __post_init__(self) -> None:
        self.type = IIOChanType((self.id >> 32) & 0xFF)


class IIOEventMonitor(contextlib.AbstractContextManager):
    def __init__(self, devname: str) -> None:
        self.devname = devname

    def __enter__(self) -> "IIOEventMonitor":
        self.file = open(self.devname, "rb")

        s = struct.Struct("L")
        buf = bytearray(s.size)
        fcntl.ioctl(self.file.fileno(), IIO_GET_EVENT_FD_IOCTL, buf)
        eventfd = s.unpack(buf)[0]
        self.eventf = open(eventfd, "rb")

        return self

    def read(self) -> IIOEvent:
        s = struct.Struct("Qq")
        buf = self.eventf.read(s.size)
        return IIOEvent(*s.unpack(buf))

    def __exit__(self, *_: Any) -> None:
        self.eventf.close()
        self.file.close()


class IIOBuffer(contextlib.AbstractContextManager):
    def __init__(self, devname: str, bufidx: int) -> None:
        self.devname = devname
        self.bufidx = bufidx

    def __enter__(self) -> "IIOBuffer":
        self.file = open(self.devname, "rb")

        s = struct.Struct("L")
        buf = bytearray(s.size)
        s.pack_into(buf, 0, self.bufidx)
        fcntl.ioctl(self.file.fileno(), IIO_BUFFER_GET_FD_IOCTL, buf)
        eventfd = s.unpack(buf)[0]
        self.eventf = open(eventfd, "rb")

        return self

    def read(self, spec: str) -> tuple:
        s = struct.Struct(spec)
        buf = self.eventf.read(s.size)
        return s.unpack(buf)

    def __exit__(self, *_: Any) -> None:
        self.eventf.close()
        self.file.close()
