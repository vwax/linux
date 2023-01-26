# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import logging
from typing import Any, Final
from unittest.mock import call

from roadtest.backend.platform import Reg32PlatformModel
from roadtest.core.devicetree import DtFragment, GpioPin, PlatformAddr
from roadtest.core.hardware import PlatformHardware
from roadtest.support.modules import Module
from roadtest.support.sysfs import PlatformDriver

logger = logging.getLogger(__name__)


REG_XDACS: Final = 0x00
REG_XDTBC: Final = 0x10
REG_XDSSA: Final = 0x14
REG_XDDSA: Final = 0x18
REG_XDDES: Final = 0x28
REG_XDDSD: Final = 0x30

REG_XDACS_XE: Final = 1 << 28

REG_XDDES_CE: Final = 1 << 28


class MilbeautXDMA(Reg32PlatformModel):
    def __init__(self, irq: GpioPin, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.irq = irq
        self.irq_active = False
        self.regs = {i: 0 for i in range(0, REG_XDDSD + 4, 4)}
        self._update_irq()

    def _update_irq(self) -> None:
        self.backend.gpio.set(self.irq, self.irq_active)

    def readl(self, addr: int) -> int:
        addr &= 0xFFFF
        logger.debug(f"readl {addr=:x} -> {self.regs[addr]:x}")
        return self.regs[addr]

    def writel(self, addr: int, value: int) -> None:
        addr &= 0xFFFF
        logger.debug(f"writel {addr=:x} {value=:x}")
        assert addr in self.regs

        self.regs[addr] = value
        self.backend.mock.reg_write(addr, value)

        if addr == REG_XDDES:
            if value & REG_XDDES_CE:
                data = self.backend.dma_read(
                    self.regs[REG_XDSSA], self.regs[REG_XDTBC] + 1
                )
                self.backend.dma_write(self.regs[REG_XDDSA], data)

                self.irq_active = True
                self._update_irq()
        elif addr == REG_XDDSD:
            self.irq_active = False
            self._update_irq()


dts = DtFragment(
    src="""
#include <dt-bindings/interrupt-controller/irq.h>

&platform {
    $dev.node$ {
            compatible = "socionext,milbeaut-m10v-xdmac";
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


def test_dma() -> None:
    with (
        PlatformHardware(MilbeautXDMA, irq=dts.gpio["gpio"]) as hw,
        PlatformDriver("milbeaut-m10v-xdmac").bind(dts.platform["dev"]),
        Module(
            "dmatest",
            params=[
                "iterations=1",
                "max_channels=1",
                "norandom=1",
                "verbose=1",
                "timeout=-1",
                "wait=1",
                "test_buf_size=4096",
                "run=1",
            ],
        ),
    ):
        hw.kick()
        mock = hw.update_mock()
        mock.reg_write.assert_has_calls(
            [
                call(REG_XDACS, REG_XDACS_XE),
                call(REG_XDTBC, 4096 - 1),
                call(REG_XDDSD, 0),
            ],
            any_order=True,
        )
