# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import abc
import dataclasses
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Type

# For I2C and GPIO we use the corresponding VirtIO devices.  For SPI,
# there is no virtio-spi so we create a SPI bus by emulating the
# SC18IS602 I2C-SPI bridge chip which already has a driver.  However,
# this chip has only four chip select lines, so we use an spi-mux
# below that powered by a gpio-mux so that we get support for loads
# more.
HEADER = """
/dts-v1/;

/ {
    #address-cells = <2>;
    #size-cells = <2>;

    chosen {
        rng-seed = /bits/ 64 <0 1 2 3 4 5 6 7>;
    };

    aliases {
        spi0 = &spi;
    };

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

            interrupt-parent = <&gpio>;

            spi-controller@9 {
                compatible = "nxp,sc18is602";
                // Address reserved by I2CAddr.Allocator
                reg = <0x08>;

                spi: spi@0 {
                    compatible = "spi-mux";
                    reg = <0>;

                    #address-cells = <1>;
                    #size-cells = <0>;

                    mux-controls = <&spi_mux>;
                };
            };
        };
    };

    virtio@2 {
        compatible = "virtio,uml";
        socket-path = "WORK/pci.sock";
        virtio-device-id = <1234>;
        ranges;

        platform: bus@0,0 {
                compatible = "virtio,device4d2", "simple-bus";
                reg = <0x00000 0 0x0 0x10000>;
                interrupt-parent = <&gpio>;
                ranges;
        };
    };

    spi_mux: mux-controller {
        compatible = "gpio-mux";
        #mux-control-cells = <0>;

        // 2**6 = 64 chip selects
        mux-gpios = <&gpio_mockup 0 0>,
                    <&gpio_mockup 1 0>,
                    <&gpio_mockup 2 0>,
                    <&gpio_mockup 3 0>,
                    <&gpio_mockup 4 0>,
                    <&gpio_mockup 5 0>;
    };

    gpio_mockup: gpio-controller {
        compatible = "gpio-mockup";

        label = "mockup";
        nr-gpios = /bits/ 16 <16>;

        gpio-controller;
        #gpio-cells = <2>;

        interrupt-controller;
        #interrupt-cells = <2>;
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


class BaseAllocator:
    @abc.abstractmethod
    def allocate(self, res: "Resource") -> int:
        ...


class NoArgAllocator(BaseAllocator):
    range = range(0)

    def __init__(self) -> None:
        self.iter = iter(self.range)

    def allocate(self, res: "Resource") -> int:
        return next(self.iter)


@dataclass
class Resource:
    val: int = -1

    class Allocator(NoArgAllocator):
        pass


@dataclass
class I2CAddr(Resource):
    bus: int = 0

    class Allocator(NoArgAllocator):
        # 0x00 - 0x07: Reserved by spec
        # 0x09: Reserved for SPI-I2C bridge
        # 0x78 - 0xFF: Reserved by spec
        range = range(0x9, 0x78)

    def __str__(self) -> str:
        return f"{self.val:02x}"


@dataclass
class GpioPin(Resource):
    class Allocator(NoArgAllocator):
        # 0 reserved for Hardware.kick() gpio-led
        # 1 reserved for serial bridges
        range = range(2, 64)

    def __str__(self) -> str:
        return f"{self.val:d}"


@dataclass
class SpiCS(Resource):
    bus: int = 0

    class Allocator(NoArgAllocator):
        range = range(0, 64)

    def __str__(self) -> str:
        return f"{self.val:02x}"


@dataclass
class PlatformAddr(Resource):
    name: str = "platform"
    size: int = 0x10000

    class Allocator:
        def __init__(self) -> None:
            # Start at non-zero so offset handling is tested even only one
            # device.
            self.next = max(0x10000, PlatformAddr.size)

        def allocate(self, res: "PlatformAddr") -> int:
            out = self.next
            self.next += res.size
            return out

    @property
    def regs(self) -> str:
        return f"0x00000 {0x10000000 + self.val:#x} 0 {self.size:#x}"

    @property
    def reg(self) -> list[int]:
        return [0x00000, 0x10000000 + self.val, 0, self.size]

    @property
    def node(self) -> str:
        return f"{self.name}@{self.val:x}"

    def __str__(self) -> str:
        return f"{0x10000000 + self.val:x}.{self.name}"


@dataclass
class NodeName(Resource):
    prefix: str = "node"

    class Allocator(NoArgAllocator):
        range = range(1, 1000)

    def __str__(self) -> str:
        return f"{self.prefix}{self.val}"


SERIAL_BRIDGE = """
#include <dt-bindings/interrupt-controller/irq.h>

&i2c {
    $SERIALVAR$: serial@$I2CVAR$ {
        compatible = "nxp,sc16is740";
        reg = <0x$I2CVAR$>;
        clock-frequency = <100000000>;

        interrupt-parent = <&gpio>;
        interrupts = <1 IRQ_TYPE_LEVEL_LOW>;
    };
};
"""


@dataclass
class SerialAddr(Resource):
    bus: int = 0
    bridge_addr: int = -1

    class Allocator(NoArgAllocator):
        # Arbitrary range, restriction is only in the bridge I2C addresses
        range = range(0, 1000)

    def __str__(self) -> str:
        return f"serial{self.val}"


class Allocators:
    def __init__(self) -> None:
        self.i2c = I2CAddr.Allocator()
        self.gpio = GpioPin.Allocator()
        self.serial = SerialAddr.Allocator()
        self.spi = SpiCS.Allocator()
        self.platform = PlatformAddr.Allocator()
        self.name = NodeName.Allocator()


class DtFragment:
    def __init__(
        self,
        src: str,
        i2c: Optional[dict[str, I2CAddr]] = None,
        gpio: Optional[dict[str, GpioPin]] = None,
        spi: Optional[dict[str, SpiCS]] = None,
        platform: Optional[dict[str, PlatformAddr]] = None,
        name: Optional[dict[str, NodeName]] = None,
        serial: Optional[dict[str, SerialAddr]] = None,
    ) -> None:
        self.src = src
        self.i2c = i2c if i2c is not None else {}
        self.gpio = gpio if gpio is not None else {}
        self.spi = spi if spi is not None else {}
        self.platform = platform if platform is not None else {}
        self.name = name if name is not None else {}
        self.serial = serial if serial is not None else {}
        self.applied = False

    def save_resources(self) -> dict:
        return {
            "i2c": [(var, dataclasses.astuple(val)) for var, val in self.i2c.items()],
            "gpio": [(var, dataclasses.astuple(val)) for var, val in self.gpio.items()],
            "spi": [(var, dataclasses.astuple(val)) for var, val in self.spi.items()],
            "name": [(var, dataclasses.astuple(val)) for var, val in self.name.items()],
            "platform": [
                (var, dataclasses.astuple(val)) for var, val in self.platform.items()
            ],
            "serial": [
                (var, dataclasses.astuple(val)) for var, val in self.serial.items()
            ],
        }

    def load_resources(self, save: Any) -> None:
        self.i2c = dict([(var, I2CAddr(*val)) for var, val in save["i2c"]])
        self.gpio = dict([(var, GpioPin(*val)) for var, val in save["gpio"]])
        self.spi = dict([(var, SpiCS(*val)) for var, val in save["spi"]])
        self.platform = dict(
            [(var, PlatformAddr(*val)) for var, val in save["platform"]]
        )
        self.name = dict([(var, NodeName(*val)) for var, val in save["name"]])
        self.serial = dict([(var, SerialAddr(*val)) for var, val in save["serial"]])

    def _apply(
        self,
        resources: Mapping[str, Resource],
        allocators: Mapping[Type[Resource], BaseAllocator],
    ) -> list[tuple[str, Resource]]:
        out = []
        for var, res in resources.items():
            res.val = allocators[res.__class__].allocate(res)
            out.append((var, res))

        return out

    def apply(
        self,
        allocators: Allocators,
    ) -> str:
        for var in self.serial.keys():
            bridgevar = f"{var}-bridge"
            assert bridgevar not in self.i2c
            self.i2c[bridgevar] = I2CAddr()

        for var, i2cres in self.i2c.items():
            i2cres.val = allocators.i2c.allocate(i2cres)
        for var, gpiores in self.gpio.items():
            gpiores.val = allocators.gpio.allocate(gpiores)
        for var, spires in self.spi.items():
            spires.val = allocators.spi.allocate(spires)
        for var, platformres in self.platform.items():
            platformres.val = allocators.platform.allocate(platformres)
        for var, nameres in self.name.items():
            nameres.val = allocators.name.allocate(nameres)

        extra = []
        for var, serialres in self.serial.items():
            bridgevar = f"{var}-bridge"
            serialres.val = allocators.serial.allocate(serialres)
            serialres.bridge_addr = self.i2c[bridgevar].val
            extra.append(
                SERIAL_BRIDGE.replace("SERIALVAR", var)
                .replace("I2CVAR", bridgevar)
                .rstrip()
            )

        src = self.src
        if extra:
            src = "\n".join(extra + [src])

        all = self.i2c | self.gpio | self.spi | self.name | self.serial | self.platform

        def repl(match: re.Match) -> str:
            var = f"{{{match.groups()[0]}}}"
            return str.format(var, **all)

        self.applied = True
        return re.sub(r"[$]([a-zA-Z0-9-_.\]\[]+)[$]", repl, src)


class FragmentManager:
    def __init__(self) -> None:
        self.allocators = Allocators()
        self.fragments: list[str] = []

    def assign(self, fragment: Optional[DtFragment]) -> None:
        if fragment is None:
            return

        if fragment.applied:
            # Multiple test functions from the same class will use
            # the same class instance
            return

        src = fragment.apply(self.allocators)
        self.fragments.append(src)


def compile(src: str, dtb: str, workdir: Path, ksrcdir: Path) -> None:
    dts = workdir / "test.dts"

    try:
        subprocess.run(
            [
                "gcc",
                "-E",
                "-nostdinc",
                f"-I{ksrcdir}/scripts/dtc/include-prefixes",
                "-undef",
                "-D__DTS__",
                "-x",
                "assembler-with-cpp",
                "-o",
                dts,
                "-",
            ],
            input=src,
            text=True,
            check=True,
            capture_output=True,
        )

        full = HEADER.replace("WORK", str(workdir)) + dts.read_text()
        dts.write_text(full)

        subprocess.run(
            ["dtc", "-I", "dts", "-O", "dtb", dts, "-o", workdir / dtb],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise Exception(f"{e.stderr}")
