# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import unittest
from typing import Any
from unittest.mock import MagicMock

from .i2c import SimpleSMBusModel, SMBusModel


class DummyModel(SMBusModel):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.regs: dict[int, int] = {}

    def reg_read(self, addr: int) -> int:
        return self.regs[addr]

    def reg_write(self, addr: int, val: int) -> None:
        self.regs[addr] = val


class TestSMBusModel(unittest.TestCase):
    def test_1(self) -> None:
        m = DummyModel(regbytes=1, backend=MagicMock())

        m.write(bytes([0x12, 0x34]))
        m.write(bytes([0x13, 0xAB, 0xCD]))

        self.assertEqual(m.regs[0x12], 0x34)
        self.assertEqual(m.regs[0x13], 0xAB)
        self.assertEqual(m.regs[0x14], 0xCD)

        m.write(bytes([0x12]))
        self.assertEqual(m.read(1), bytes([0x34]))

        m.write(bytes([0x12]))
        self.assertEqual(m.read(3), bytes([0x34, 0xAB, 0xCD]))

    def test_2big(self) -> None:
        m = DummyModel(regbytes=2, byteorder="big", backend=MagicMock())

        m.write(bytes([0x12, 0x34, 0x56, 0xAB, 0xCD]))
        self.assertEqual(m.regs[0x12], 0x3456)
        self.assertEqual(m.regs[0x14], 0xABCD)

        m.write(bytes([0x12]))
        self.assertEqual(m.read(2), bytes([0x34, 0x56]))

        m.write(bytes([0x14]))
        self.assertEqual(m.read(2), bytes([0xAB, 0xCD]))

        m.write(bytes([0x12]))
        self.assertEqual(m.read(4), bytes([0x34, 0x56, 0xAB, 0xCD]))

    def test_2little(self) -> None:
        m = DummyModel(regbytes=2, byteorder="little", backend=MagicMock())

        m.write(bytes([0x12, 0x34, 0x56, 0xAB, 0xCD]))
        self.assertEqual(m.regs[0x12], 0x5634)
        self.assertEqual(m.regs[0x14], 0xCDAB)

        m.write(bytes([0x12]))
        self.assertEqual(m.read(2), bytes([0x34, 0x56]))


class TestSimpleSMBusModel(unittest.TestCase):
    def test_simple(self) -> None:
        m = SimpleSMBusModel(
            regs={0x01: 0x12, 0x02: 0x34},
            regbytes=1,
            backend=MagicMock(),
        )
        self.assertEqual(m.reg_read(0x01), 0x12)
        self.assertEqual(m.reg_read(0x02), 0x34)

        m.reg_write(0x01, 0x56)
        self.assertEqual(m.reg_read(0x01), 0x56)
        self.assertEqual(m.reg_read(0x02), 0x34)

        with self.assertRaises(Exception):
            m.reg_write(0x03, 0x00)
        with self.assertRaises(Exception):
            m.reg_read(0x03)
