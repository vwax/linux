# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import enum
import subprocess
from pathlib import Path
from typing import Any, Optional

HEADER = """
/dts-v1/;

/ {
    #address-cells = <2>;
    #size-cells = <2>;

    virtio@0 {
        compatible = "virtio,uml";
        socket-path = "WORK/gpio.sock";
        virtio-device-id = <0x29>;

        gpio: gpio {
            compatible = "virtio,device29";

            gpio-controller;
            #gpio-cells = <2>;

            interrupt-controller;
            #interrupt-cells = <2>;
        };
    };

    virtio@1 {
        compatible = "virtio,uml";
        socket-path = "WORK/i2c.sock";
        virtio-device-id = <0x22>;

        i2c: i2c {
            compatible = "virtio,device22";

            #address-cells = <1>;
            #size-cells = <0>;
        };
    };

    // See Hardware.kick()
    leds {
        compatible = "gpio-leds";
        led0 {
            gpios = <&gpio 0 0>;
        };
    };
};
"""


class DtVar(enum.Enum):
    I2C_ADDR = 0
    GPIO_PIN = 1


class DtFragment:
    def __init__(self, src: str, variables: Optional[dict[str, DtVar]] = None) -> None:
        self.src = src
        if not variables:
            variables = {}
        self.variables = variables
        self.values: dict[str, int] = {}

    def apply(self, values: dict[str, Any]) -> str:
        src = self.src

        for var in self.variables.keys():
            typ = self.variables[var]
            val = values[var]

            if typ == DtVar.I2C_ADDR:
                str = f"{val:02x}"
            elif typ == DtVar.GPIO_PIN:
                str = f"{val:d}"

            src = src.replace(f"${var}$", str)

        self.values = values
        return src

    def __getitem__(self, key: str) -> Any:
        return self.values[key]


class Devicetree:
    def __init__(self, workdir: Path, ksrcdir: Path) -> None:
        self.workdir: Path = workdir
        self.ksrcdir: Path = ksrcdir
        self.next_i2c_addr: int = 0x1
        # 0 is used for gpio-leds for Hardware.kick()
        self.next_gpio_pin: int = 1
        self.src: str = ""

    def assemble(self, fragments: list[DtFragment]) -> None:
        parts = []
        for fragment in fragments:
            if fragment.values:
                # Multiple test functions from the same class will use
                # the same class instance
                continue

            values = {}

            for var, type in fragment.variables.items():
                if type == DtVar.I2C_ADDR:
                    values[var] = self.next_i2c_addr
                    self.next_i2c_addr += 1
                elif type == DtVar.GPIO_PIN:
                    values[var] = self.next_gpio_pin
                    self.next_gpio_pin += 1

            parts.append(fragment.apply(values))

        self.src = "\n".join(parts)

    def compile(self, dtb: str) -> None:
        dts = self.workdir / "test.dts"

        try:
            subprocess.run(
                [
                    "gcc",
                    "-E",
                    "-nostdinc",
                    f"-I{self.ksrcdir}/scripts/dtc/include-prefixes",
                    "-undef",
                    "-D__DTS__",
                    "-x",
                    "assembler-with-cpp",
                    "-o",
                    dts,
                    "-",
                ],
                input=self.src,
                text=True,
                check=True,
                capture_output=True,
            )

            full = HEADER.replace("WORK", str(self.workdir)) + dts.read_text()
            dts.write_text(full)

            subprocess.run(
                ["dtc", "-I", "dts", "-O", "dtb", dts, "-o", self.workdir / dtb],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise Exception(f"{e.stderr}")
