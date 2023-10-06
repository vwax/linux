# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import contextlib
from pathlib import Path
from typing import Any, Final, Iterator
from unittest.mock import call

from roadtest.backend.platform import Reg32PlatformModel
from roadtest.core.devicetree import DtFragment, PlatformAddr
from roadtest.core.hardware import PlatformHardware
from roadtest.support.sysfs import PlatformDriver, read_int, write_int, write_str

REG_DIROUT: Final = 0x00
REG_DAT: Final = 0x04


class GpioMMIO(Reg32PlatformModel):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.regs = {
            REG_DIROUT: 0,
            REG_DAT: 0,
        }

    def readl(self, addr: int) -> int:
        return self.regs[addr]

    def writel(self, addr: int, value: int) -> None:
        assert addr in self.regs
        self.regs[addr] = value


dts = DtFragment(
    src="""
#include <dt-bindings/interrupt-controller/irq.h>

&platform {
    $dev.node$ {
            compatible = "wd,mbl-gpio";
            reg-names = "dirout", "dat";
            reg = <$dev.reg[0]$ ($dev.reg[1]$+0) $dev.reg[2]$ 0x4>,
                  <$dev.reg[0]$ ($dev.reg[1]$+4) $dev.reg[2]$ 0x4>;
            gpio-controller;
            #gpio-cells = <2>;
    };
};
""",
    platform={
        "dev": PlatformAddr(),
    },
)


@contextlib.contextmanager
def gpio_export(pin: int) -> Iterator[Path]:
    top = Path("/sys/class/gpio")
    write_int((top / "export"), pin)
    try:
        yield top / f"gpio{pin}"
    finally:
        write_int((top / "unexport"), pin)


def test_out_value() -> None:
    with (
        PlatformHardware(GpioMMIO) as hw,
        PlatformDriver("basic-mmio-gpio").bind(dts.platform["dev"]) as dev,
    ):
        gpiochip = next(dev.path.glob("gpio/gpio*"))
        base = read_int(gpiochip / "base")

        with gpio_export(base + 0) as gpath:
            write_str(gpath / "direction", "out")
            write_int(gpath / "value", 1)
            write_int(gpath / "value", 0)
            read_int(gpath / "value")

            mock = hw.update_mock()
            mock.assert_has_calls(
                [
                    call.reg_write(REG_DIROUT, 1),
                    call.reg_write(REG_DAT, 1),
                    call.reg_write(REG_DAT, 0),
                ]
            )
