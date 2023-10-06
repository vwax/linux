# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import termios
from pathlib import Path
from unittest.mock import call

from roadtest.backend.serial import SerialModel
from roadtest.core.devicetree import DtFragment, GpioPin, I2CAddr
from roadtest.core.hardware import I2CHardware
from roadtest.support.sysfs import I2CDriver


class NoopSerialModel(SerialModel):
    def recv(self, data: bytes) -> None:
        pass


dts = DtFragment(
    src="""
#include <dt-bindings/interrupt-controller/irq.h>

&i2c {
    serial@$serial$ {
        compatible = "nxp,sc16is740";
        reg = <0x$serial$>;
        clock-frequency = <100000000>;

        interrupt-parent = <&gpio>;
        interrupts = <$irq$ IRQ_TYPE_LEVEL_LOW>;
    };
};
    """,
    gpio={
        "irq": GpioPin(),
    },
    i2c={
        "serial": I2CAddr(),
    },
)


def test_serial() -> None:
    with (
        I2CHardware(NoopSerialModel, bridge_irq=dts.gpio["irq"]) as hw,
        I2CDriver("sc16is7xx").bind(dts.i2c["serial"]) as dev,
    ):
        ttyname = next(dev.path.glob("tty/tty*")).stem
        writedata = b"ABCD" * 129
        readdata = b"1234"

        with Path(f"/dev/{ttyname}").open("r+b", buffering=0) as tty:
            fd = tty.fileno()
            attr = termios.tcgetattr(fd)
            attr[3] = attr[3] & ~(termios.ECHO | termios.ICANON)
            termios.tcsetattr(fd, termios.TCSANOW, attr)

            tty.write(writedata)
            termios.tcdrain(fd)
            hw.update_mock().recv.assert_has_calls(
                [
                    call(
                        b"ABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCD"
                    ),
                    call(
                        b"ABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCD"
                    ),
                    call(
                        b"ABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCD"
                    ),
                    call(
                        b"ABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCD"
                    ),
                    call(
                        b"ABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCD"
                    ),
                    call(
                        b"ABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCD"
                    ),
                    call(
                        b"ABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCD"
                    ),
                    call(
                        b"ABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCDABCD"
                    ),
                    call(b"ABCD"),
                ]
            )

            hw.model.tx(readdata)
            hw.kick()
            assert tty.read(len(readdata)) == readdata
