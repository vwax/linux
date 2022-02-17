# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import contextlib
from pathlib import Path
from typing import Iterator


# Path.write_text() is inappropriate since Python calls write(2)
# a second time if the first one returns an error, if the file
# was opened as text.
def write_str(path: Path, val: str) -> None:
    path.write_bytes(val.encode())


def write_int(path: Path, val: int) -> None:
    write_str(path, str(val))


def write_float(path: Path, val: float) -> None:
    write_str(path, str(val))


def read_str(path: Path) -> str:
    return path.read_text().rstrip()


def read_int(path: Path) -> int:
    return int(read_str(path))


def read_float(path: Path) -> float:
    return float(read_str(path))


class I2CDevice:
    def __init__(self, addr: int, bus: int = 0) -> None:
        self.id = f"{bus}-{addr:04x}"
        self.path = Path(f"/sys/bus/i2c/devices/{self.id}")


class PlatformDevice:
    def __init__(self, name: str) -> None:
        self.id = name
        self.path = Path(f"/sys/bus/platform/devices/{self.id}")


class I2CDriver:
    def __init__(self, driver: str) -> None:
        self.driver = driver
        self.path = Path(f"/sys/bus/i2c/drivers/{driver}")

    @contextlib.contextmanager
    def bind(self, addr: int, bus: int = 0) -> Iterator[I2CDevice]:
        dev = I2CDevice(addr, bus)
        write_str(self.path / "bind", dev.id)

        try:
            yield dev
        finally:
            write_str(self.path / "unbind", dev.id)


class PlatformDriver:
    def __init__(self, driver: str) -> None:
        self.driver = driver
        self.path = Path(f"/sys/bus/platform/drivers/{driver}")

    @contextlib.contextmanager
    def bind(self, addr: str) -> Iterator[PlatformDevice]:
        dev = PlatformDevice(addr)
        write_str(self.path / "bind", dev.id)

        try:
            yield dev
        finally:
            write_str(self.path / "unbind", dev.id)
