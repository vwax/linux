# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import logging
from pathlib import Path
import subprocess
import termios
from typing import Any, Final, Type

from roadtest import ENV_KSRC_DIR
from roadtest.backend.platform import PlatformModel, Reg32PlatformModel
from roadtest.backend.spi import SPIModel
from roadtest.core.devicetree import DtFragment, GpioPin, PlatformAddr
from roadtest.core.hardware import PlatformHardware
from roadtest.support.sysfs import PlatformDriver

logger = logging.getLogger(__name__)

REG_BYTES_READY: Final = 0x04
REG_CMD: Final = 0x08
REG_DATA_PTR: Final = 0x10
REG_DATA_LEN: Final = 0x14
REG_DATA_PTR_HIGH: Final = 0x18
REG_VERSION: Final = 0x20

CMD_INT_DISABLE: Final = 0
CMD_INT_ENABLE: Final = 1
CMD_WRITE_BUFFER: Final = 2
CMD_READ_BUFFER: Final = 3


class GoldfishTTY(Reg32PlatformModel):
    def __init__(self, irq: GpioPin, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.buffer = bytearray()
        self.irq = irq
        self.irq_enabled = False
        self.regs = {
            REG_BYTES_READY: 0x00,
            REG_CMD: 0x00,
            REG_DATA_PTR: 0x00,
            REG_DATA_LEN: 0x00,
            REG_DATA_PTR_HIGH: 0x00,
            # Ranchu version which uses DMA addresses
            REG_VERSION: 0x01,
        }
        # self._update_irq()

    def _update_irq(self) -> None:
        self.regs[REG_BYTES_READY] = len(self.buffer)
        self.backend.gpio.set(self.irq, self.irq_enabled and len(self.buffer) > 0)

    def tx(self, data: bytes) -> None:
        self.buffer += data
        self._update_irq()

    def readl(self, addr: int) -> int:
        addr &= 0xFFFF
        logger.debug(f"readl {addr=:x} -> {self.regs[addr]}")
        return self.regs[addr]

    def writel(self, addr: int, value: int) -> None:
        addr &= 0xFFFF
        logger.debug(f"writel {addr=:x} {value=:x}")
        assert addr in self.regs
        self.regs[addr] = value

        if addr == REG_CMD:
            if value == CMD_INT_DISABLE:
                self.irq_enabled = False
                self._update_irq()
            elif value == CMD_INT_ENABLE:
                self.irq_enabled = True
                self._update_irq()
            elif value == CMD_WRITE_BUFFER:
                dma_len = self.regs[REG_DATA_LEN]
                dma_addr = (self.regs[REG_DATA_PTR_HIGH] << 32) | self.regs[
                    REG_DATA_PTR
                ]

                logger.debug(f"write buffer {dma_addr=:x} {dma_len=:x}")
                data = self.backend.dma_read(dma_addr, dma_len)
                self.backend.mock.recv(data)
                logger.debug(f"{data!r}")
            elif value == CMD_READ_BUFFER:
                dma_len = self.regs[REG_DATA_LEN]
                dma_addr = (self.regs[REG_DATA_PTR_HIGH] << 32) | self.regs[
                    REG_DATA_PTR
                ]

                logger.debug(
                    f"read buffer {dma_addr=:x} {dma_len=:x} {bytes(self.buffer[:dma_len])!r}"
                )

                self.backend.dma_write(dma_addr, self.buffer[:dma_len])
                del self.buffer[:dma_len]
                self._update_irq()


dts = DtFragment(
    src="""
#include <dt-bindings/interrupt-controller/irq.h>

&platform {
    $dev.node$ {
            compatible = "google,goldfish-tty";
            reg = <$dev.regs$>;
            interrupts = <$gpio$ IRQ_TYPE_LEVEL_HIGH>;
    };
};
""",
    platform={
        "dev": PlatformAddr(),
    },
    gpio={
        "gpio": GpioPin(),
    },
)


def test_foo() -> None:
    with (
        PlatformHardware(GoldfishTTY, irq=dts.gpio["gpio"]) as hw,
        PlatformDriver("goldfish_tty").bind(dts.platform["dev"]) as dev,
    ):
        data = b"ABCD"
        with Path("/dev/ttyGF0").open("r+b", buffering=0) as tty:
            # Note that echoing is actually broken in this driver since it
            # does DMA to the buffer it gets from tty_prepare_flip_string(),
            # which is a vmalloc()'d buffer in the __process_echoes() path.
            fd = tty.fileno()
            attr = termios.tcgetattr(fd)
            attr[3] = attr[3] & ~(termios.ECHO | termios.ICANON)
            termios.tcsetattr(fd, termios.TCSANOW, attr)

            #tty.write(data)
            hw.model.tx(b"12345")
            hw.kick()
            assert tty.read(10) == b"12345"

        #     print(tty.read(10))
        #     hw.model.tx(b"67890")
        #     hw.kick()
        #     print(tty.read(10))

        # hw.update_mock().recv.assert_called_once_with(data)
        # gotdata = b"".join([call[0][0] for call in hw.update_mock().recv.call_args_list])
        # assert not gotdata


# def test_illuminance(self) -> None:
#     with (
#         PlatformHardware(GoldfishTTY, irq=10) as hw,
#         PlatformDriver("goldfish_tty").bind("f0010000.foo") as dev,
#     ):
#         data = b"ABCD"
#         with Path("/dev/ttyGF0").open("r+b", buffering=0) as tty:
#             # Note that echoing is actually broken in this driver since it
#             # does DMA to the buffer it gets from tty_prepare_flip_string(),
#             # which is a vmalloc()'d buffer in the __process_echoes() path.
#             fd = tty.fileno()
#             attr = termios.tcgetattr(fd)
#             attr[3] = attr[3] & ~(termios.ECHO | termios.ICANON)
#             termios.tcsetattr(fd, termios.TCSANOW, attr)

#             tty.write(data)
#             hw.tx(b"12345")
#             hw.kick()
#             print(tty.read(10))
#             hw.tx(b"67890")
#             hw.kick()
#             print(tty.read(10))

#         hw.update_mock().recv.assert_called_once_with(data)
#         # gotdata = b"".join([call[0][0] for call in mock.recv.call_args_list])
#         self.fail()
