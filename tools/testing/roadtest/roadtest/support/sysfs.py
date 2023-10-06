# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import contextlib
from pathlib import Path
from typing import Any, Iterator, Union

from roadtest.core.devicetree import I2CAddr, NodeName, PlatformAddr, SerialAddr, SpiCS
from roadtest.support.modules import load_modules, modprobe


# Path.write_text() is inappropriate since Python calls write(2)
# a second time if the first one returns an error, if the file
# was opened as text.
def write_str(path: Path, val: str) -> None:
    path.write_bytes(val.encode())


def write_int(path: Path, val: int) -> None:
    write_str(path, str(val))


def write_bool(path: Path, val: bool) -> None:
    write_str(path, "1" if val else "0")


def write_float(path: Path, val: float) -> None:
    write_str(path, str(val))


def read_str(path: Path) -> str:
    return path.read_text().rstrip()


def read_int(path: Path) -> int:
    return int(read_str(path))


def read_bool(path: Path) -> bool:
    return True if read_str(path) in ["Y", "y", "1"] else False


def read_float(path: Path) -> float:
    return float(read_str(path))


@contextlib.contextmanager
def set_module_params(modname: str, **kwargs: Any) -> Iterator:
    modpath = Path("/sys/module/") / modname
    if not modpath.exists():
        modprobe(modname)

    orig = {}
    paths = {}
    for param in kwargs.keys():
        paths[param] = path = Path(modpath) / "parameters" / param
        orig[param] = read_str(path)
    try:
        for param, val in kwargs.items():
            write_str(paths[param], str(val))

        yield
    finally:
        for param, origval in orig.items():
            write_str(paths[param], origval)


class I2CDevice:
    def __init__(self, addr: I2CAddr) -> None:
        self.id = f"{addr.bus}-{addr.val:04x}"
        self.path = Path(f"/sys/bus/i2c/devices/{self.id}")

    def get_subdev(self, name: str) -> str:
        return next(self.path.glob(f"*:{name}")).name


class PlatformDevice:
    def __init__(self, name: str) -> None:
        self.id = name
        self.path = Path(f"/sys/bus/platform/devices/{self.id}")


class I2CDriver:
    def __init__(self, driver: str) -> None:
        self.driver = driver
        self.path = Path(f"/sys/bus/i2c/drivers/{driver}")

    @contextlib.contextmanager
    def bind(self, addr: I2CAddr) -> Iterator[I2CDevice]:
        dev = I2CDevice(addr)
        write_str(self.path / "bind", dev.id)

        load_modules(dev.path.glob("**/modalias"))

        try:
            yield dev
        finally:
            write_str(self.path / "unbind", dev.id)


class SPIDevice:
    def __init__(self, addr: SpiCS) -> None:
        self.id = f"spi{addr.bus}.{addr.val}"
        self.path = Path(f"/sys/bus/spi/devices/{self.id}")


class SPIDriver:
    def __init__(self, driver: str) -> None:
        self.driver = driver
        self.path = Path(f"/sys/bus/spi/drivers/{driver}")

    @contextlib.contextmanager
    def bind(self, addr: SpiCS) -> Iterator[SPIDevice]:
        dev = SPIDevice(addr)
        write_str(self.path / "bind", dev.id)

        try:
            yield dev
        finally:
            write_str(self.path / "unbind", dev.id)


class SerialDevice:
    def __init__(self, addr: SerialAddr) -> None:
        # The serdev bus number is managed by an idr so the number
        # is always zero if no other busses are active (this is
        # the serial0 part of the id below)
        #
        # And only one device is supported by serialdev (the -0 part)
        self.id = "serial0-0"
        self.path = Path(f"/sys/bus/serial/devices/{self.id}")

    def get_subdev(self, name: str) -> str:
        return next(self.path.glob(f"*:{name}")).name


class SerialDriver:
    def __init__(self, driver: str) -> None:
        self.driver = driver
        self.path = Path(f"/sys/bus/serial/drivers/{driver}")

    @contextlib.contextmanager
    def bind(self, addr: SerialAddr) -> Iterator[SerialDevice]:
        dev = SerialDevice(addr)
        with I2CDriver("sc16is7xx").bind(I2CAddr(addr.bridge_addr)):
            write_str(self.path / "bind", dev.id)

            load_modules(dev.path.glob("**/modalias"))

            try:
                yield dev
            finally:
                write_str(self.path / "unbind", dev.id)


class PlatformDriver:
    def __init__(self, driver: str) -> None:
        self.driver = driver
        self.path = Path(f"/sys/bus/platform/drivers/{driver}")

    @contextlib.contextmanager
    def bind(
        self, addr: Union[str, NodeName, PlatformAddr]
    ) -> Iterator[PlatformDevice]:
        dev = PlatformDevice(str(addr))
        write_str(self.path / "bind", dev.id)

        try:
            yield dev
        finally:
            write_str(self.path / "unbind", dev.id)
