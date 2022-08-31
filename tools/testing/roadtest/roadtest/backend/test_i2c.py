# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from typing import Any
from unittest.mock import MagicMock

import pytest

from .i2c import SimpleSMBusModel, SMBusModel


class DummyModel(SMBusModel):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.regs: dict[int, int] = {}

    def reg_read(self, addr: int) -> int:
        return self.regs[addr]

    def reg_write(self, addr: int, val: int) -> None:
        self.regs[addr] = val


def test_1() -> None:
    m = DummyModel(regbytes=1, backend=MagicMock())

    m.write(bytes([0x12, 0x34]))
    m.write(bytes([0x13, 0xAB, 0xCD]))

    assert m.regs[0x12] == 0x34
    assert m.regs[0x13] == 0xAB
    assert m.regs[0x14] == 0xCD

    m.write(bytes([0x12]))
    assert m.read(1) == bytes([0x34])

    m.write(bytes([0x12]))
    assert m.read(3) == bytes([0x34, 0xAB, 0xCD])


def test_2big() -> None:
    m = DummyModel(regbytes=2, byteorder="big", backend=MagicMock())

    m.write(bytes([0x12, 0x34, 0x56, 0xAB, 0xCD]))
    assert m.regs[0x12] == 0x3456
    assert m.regs[0x14] == 0xABCD

    m.write(bytes([0x12]))
    assert m.read(2) == bytes([0x34, 0x56])

    m.write(bytes([0x14]))
    assert m.read(2) == bytes([0xAB, 0xCD])

    m.write(bytes([0x12]))
    assert m.read(4) == bytes([0x34, 0x56, 0xAB, 0xCD])


def test_2little() -> None:
    m = DummyModel(regbytes=2, byteorder="little", backend=MagicMock())

    m.write(bytes([0x12, 0x34, 0x56, 0xAB, 0xCD]))
    assert m.regs[0x12] == 0x5634
    assert m.regs[0x14] == 0xCDAB

    m.write(bytes([0x12]))
    assert m.read(2) == bytes([0x34, 0x56])


def test_simple() -> None:
    m = SimpleSMBusModel(
        regs={0x01: 0x12, 0x02: 0x34},
        regbytes=1,
        backend=MagicMock(),
    )
    assert m.reg_read(0x01) == 0x12
    assert m.reg_read(0x02) == 0x34

    m.reg_write(0x01, 0x56)
    assert m.reg_read(0x01) == 0x56
    assert m.reg_read(0x02) == 0x34

    with pytest.raises(Exception):
        m.reg_write(0x03, 0x00)
    with pytest.raises(Exception):
        m.reg_read(0x03)
