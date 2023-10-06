# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import abc
import logging
from typing import Any, Final

from roadtest.backend.i2c import NonFlakyI2CModel
from roadtest.core.devicetree import GpioPin

REG_RHR: Final = 0x0
REG_THR: Final = REG_RHR

REG_IER: Final = 0x1
REG_IER_RHR: Final = 1 << 0
REG_IER_THR: Final = 1 << 1

REG_FCR: Final = 0x2

REG_IIR: Final = REG_FCR
REG_IIR_NOT_PENDING: Final = 1 << 0
REG_IIR_SRC_RHR = 0b000100
REG_IIR_SRC_THR = 0b000010

REG_LCR: Final = 0x3
REG_MCR: Final = 0x4
REG_LSR: Final = 0x5
REG_TCR: Final = 0x6
REG_TXLVL: Final = 0x8
REG_RXLVL: Final = 0x9
REG_IOCONTROL: Final = 0xE
REG_EFCR: Final = 0xF


logger = logging.getLogger(__name__)

# The debug prints are useful for debugging this model itself, but
# uninteresting for users of the SerialModel so disable them by
# default.
logger.setLevel(logging.INFO)


class SerialModel(NonFlakyI2CModel):
    def __init__(self, bridge_irq: GpioPin, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.buffer = bytearray()
        self.irq = bridge_irq
        self._set_irq(False)
        self.trigger_thr = False
        self.reg_addr = 0
        self.bridge_regs = {
            REG_RHR: 0x00,
            REG_IER: 0x00,
            REG_FCR: 0x00,
            REG_LCR: 0x00,
            REG_MCR: 0x00,
            REG_LSR: 0x00,
            REG_TCR: 0x00,
            REG_TXLVL: 64,
            REG_RXLVL: 0x00,
            REG_IOCONTROL: 0x00,
            REG_EFCR: 0x00,
        }

    def _set_irq(self, active: int) -> None:
        # Active-low
        self.backend.gpio.set(self.irq, not active)

    def _get_irq_src(self) -> int:
        # Use one less than the FIFO size to avoid "potential overflow" warnings
        # from the driver.
        rxlvl = min(63, len(self.buffer))
        logger.debug(f"{self.buffer=} {rxlvl=}")
        self.bridge_regs[REG_RXLVL] = rxlvl

        ier = self.bridge_regs[REG_IER]
        src = 0
        if rxlvl > 0 and (ier & REG_IER_RHR):
            src = REG_IIR_SRC_RHR
        elif (ier & REG_IER_THR) and self.trigger_thr:
            src = REG_IIR_SRC_THR

        return src

    def _update_irq(self) -> None:
        src = self._get_irq_src()
        logger.debug(f"update_irq {src=:x}")
        self._set_irq(src != 0)

    def tx(self, data: bytes) -> None:
        self.buffer += data
        self._update_irq()

    # Ignore special and enhanced register sets
    def _ignore(self, addr: int) -> bool:
        lcr = self.bridge_regs[REG_LCR]
        if lcr & (1 << 7) and addr <= 1:
            return True
        elif lcr == 0xBF and addr in [2, 4, 5, 6, 7]:
            return True

        return False

    def reg_read(self, addr: int, len: int) -> bytes:
        logger.debug(f"readx {addr=:x}")

        if self._ignore(addr):
            return bytes(len)

        if addr == REG_RHR:
            logger.debug(f"read buffer {addr=:x} {len=:x} {bytes(self.buffer[:len])!r}")
            data = self.buffer[:len]
            del self.buffer[:len]
            self._update_irq()
            return bytes(data)
            logger
        elif addr == REG_IIR:
            value = REG_IIR_NOT_PENDING
            src = self._get_irq_src()
            if src:
                value = src
                if src == REG_IIR_SRC_THR:
                    self.trigger_thr = False
            logger.debug(f"value {value=:x}")
            return bytes([value])

        if addr == REG_RXLVL:
            logger.debug(f"rxlvl read {self.bridge_regs[addr]}")

        logger.debug(f"{addr=:x} {self.bridge_regs[addr]:x}")

        return bytes([self.bridge_regs[addr]])

    @abc.abstractmethod
    def recv(self, data: bytes) -> None:
        pass

    def send(self, data: bytes) -> None:
        self.buffer += data
        self._update_irq()

    def reg_write(self, addr: int, data: bytes) -> None:
        # Ignore special and enhanced register sets
        if self._ignore(addr):
            return

        if addr == REG_THR:
            self.trigger_thr = True

            self.backend.mock.recv(data)
            self.recv(data)
            self._update_irq()
            return

        assert addr in self.bridge_regs
        self.bridge_regs[addr] = data[0]
        if addr == REG_IER:
            self._update_irq()

    def read(self, len: int) -> bytes:
        return self.reg_read(self.reg_addr, len)

    def write(self, data: bytes) -> None:
        self.reg_addr = addr = data[0] >> 3
        if len(data) > 1:
            self.backend.mock.reg_write(addr, data[1:])
            self.reg_write(addr, data[1:])
