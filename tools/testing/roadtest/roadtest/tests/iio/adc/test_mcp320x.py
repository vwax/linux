# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import contextlib
import logging
import random
from pathlib import Path
from typing import Any, Final, Iterator, Sequence

import pytest

from roadtest.backend.spi import SPIModel
from roadtest.core.devicetree import DtFragment, NodeName, SpiCS
from roadtest.core.hardware import SPIHardware
from roadtest.core.suite import flaky_bus
from roadtest.support.sysfs import SPIDriver, read_int, write_int, write_str
from roadtest.tests.iio import iio
from roadtest.tests.iio.iio import IIODevice

logger = logging.getLogger(__name__)


class MCP3008(SPIModel):
    def __init__(self, numchans=8, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.numchans = numchans
        self.values = [0] * numchans * 2

    def xfer(self, indata: bytes) -> bytes:
        logger.debug(f"{indata=}")

        startpos = 0
        for i in reversed(range(8)):
            if indata[0] & (1 << i):
                startpos = i
                break

        singlepos = startpos - 1
        single = bool(indata[0] & (1 << singlepos))

        datapos = singlepos - 3
        channel = (indata[0] >> datapos) & 0x7

        if not single:
            channel += self.numchans

        value = self.values[channel]
        outdata = bytes([0, value >> 2, (value & 0x3) << 6])

        logger.debug(f"{channel=} {outdata[0]:02x} {outdata[1]:02x}")
        return outdata

    def set_value(self, chan: int, value: int) -> None:
        self.values[chan] = value


class MCP320xSingleChannelModel(SPIModel):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.value = 0

    def set_value(self, value: int) -> None:
        self.value = value


class MCP3001(MCP320xSingleChannelModel):
    def xfer(self, _: bytes) -> bytes:
        return bytes([self.value >> 5, (self.value << 3) & 0xFF])


class MCP3002(SPIModel):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.values = [0] * 4

    def xfer(self, indata: bytes) -> bytes:
        rx = indata[0]

        assert rx & (1 << 4)
        single = bool(rx & (1 << 3))
        odd = bool(rx & (1 << 2))

        channel = int(odd)
        if not single:
            channel += 2

        value = self.values[channel]
        return bytes([0, value >> 2, (value << 6) & 0xFF])

    def set_value(self, chan: int, value: int) -> None:
        self.values[chan] = value


# Combined datasheet so subclass it
class MCP3004(MCP3008):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(numchans=4, **kwargs)


class MCP3201(MCP320xSingleChannelModel):
    def xfer(self, _: bytes) -> bytes:
        return bytes([self.value >> 7, (self.value << 1) & 0xFF])


class MCP3202(SPIModel):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.values = [0] * 4

    def xfer(self, indata: bytes) -> bytes:
        rx = indata[0]

        assert rx & (1 << 4)
        single = bool(rx & (1 << 3))
        odd = bool(rx & (1 << 2))

        channel = int(odd)
        if not single:
            channel += 2

        value = self.values[channel]
        return bytes([0, value >> 4, (value << 4) & 0xFF])

    def set_value(self, chan: int, value: int) -> None:
        self.values[chan] = value


class MCP3208(SPIModel):
    def __init__(self, numchans=8, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.numchans = numchans
        self.values = [0] * numchans * 2

    def xfer(self, indata: bytes) -> bytes:
        logger.debug(f"{indata=}")

        startpos = 0
        for i in reversed(range(8)):
            if indata[0] & (1 << i):
                startpos = i
                break

        singlepos = startpos - 1
        single = bool(indata[0] & (1 << singlepos))

        datapos = singlepos - 3
        channel = (indata[0] >> datapos) & 0x7

        if not single:
            channel += self.numchans

        value = self.values[channel]
        outdata = bytes([0, value >> 4, (value << 4) & 0xFF])

        logger.debug(f"{channel=} {outdata[0]:02x} {outdata[1]:02x}")
        return outdata

    def set_value(self, chan: int, value: int) -> None:
        self.values[chan] = value


# Combined datasheet so subclass it
class MCP3204(MCP3208):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(numchans=4, **kwargs)


class MCP3301(MCP320xSingleChannelModel):
    def xfer(self, _: bytes) -> bytes:
        return bytes([self.value >> 8, self.value & 0xFF])


class MCP3550_50(MCP320xSingleChannelModel):
    def xfer(self, _: bytes) -> bytes:
        return bytes(
            [(self.value >> 16) & 0xFF, (self.value >> 8) & 0xFF, self.value & 0xFF]
        )


# Only conversion time is differs in these
class MCP3550_60(MCP3550_50):
    pass


class MCP3551(MCP3550_50):
    pass


class MCP3553(MCP3550_50):
    pass


dts = DtFragment(
    src="""
&spi {
    foo@$mcp3001$ {
        compatible = "microchip,mcp3001";
        reg = <0x$mcp3001$>;
        vref-supply = <&$vref$>;
    };

    foo@$mcp3002$ {
        compatible = "microchip,mcp3002";
        reg = <0x$mcp3002$>;
        vref-supply = <&$vref$>;
    };

    foo@$mcp3004$ {
        compatible = "microchip,mcp3004";
        reg = <0x$mcp3004$>;
        vref-supply = <&$vref$>;
    };

    foo@$mcp3008$ {
        compatible = "microchip,mcp3008";
        reg = <0x$mcp3008$>;
        vref-supply = <&$vref$>;
    };

    foo@$mcp3201$ {
        compatible = "microchip,mcp3201";
        reg = <0x$mcp3201$>;
        vref-supply = <&$vref$>;
    };

    foo@$mcp3202$ {
        compatible = "microchip,mcp3202";
        reg = <0x$mcp3202$>;
        vref-supply = <&$vref$>;
    };

    foo@$mcp3204$ {
        compatible = "microchip,mcp3204";
        reg = <0x$mcp3204$>;
        vref-supply = <&$vref$>;
    };

    foo@$mcp3208$ {
        compatible = "microchip,mcp3208";
        reg = <0x$mcp3208$>;
        vref-supply = <&$vref$>;
    };

    foo@$mcp3301$ {
        compatible = "microchip,mcp3301";
        reg = <0x$mcp3301$>;
        vref-supply = <&$vref$>;
        spi-cpol;
    };

    foo@$mcp3550-50$ {
        compatible = "microchip,mcp3550-50";
        reg = <0x$mcp3550-50$>;
        vref-supply = <&$vref$>;
        spi-cpol;
    };

    foo@$mcp3550-60$ {
        compatible = "microchip,mcp3550-60";
        reg = <0x$mcp3550-60$>;
        vref-supply = <&$vref$>;
        spi-cpol;
    };

    foo@$mcp3551$ {
        compatible = "microchip,mcp3551";
        reg = <0x$mcp3551$>;
        vref-supply = <&$vref$>;
        spi-cpol;
    };

    foo@$mcp3553$ {
        compatible = "microchip,mcp3553";
        reg = <0x$mcp3553$>;
        vref-supply = <&$vref$>;
        // Setting CPOL allows us to use the hex values from Figure 5-1 of the datasheet
        // without modification.
        spi-cpol;
    };
};

/ {
    $vref$: $vref$ {
                compatible = "regulator-fixed";
                regulator-name = "vmmc";
                regulator-min-microvolt = <3300000>;
                regulator-max-microvolt = <3300000>;
    };
};
        """,
    spi={
        "mcp3001": SpiCS(),
        "mcp3002": SpiCS(),
        "mcp3004": SpiCS(),
        "mcp3008": SpiCS(),
        "mcp3201": SpiCS(),
        "mcp3202": SpiCS(),
        "mcp3204": SpiCS(),
        "mcp3208": SpiCS(),
        "mcp3301": SpiCS(),
        "mcp3550-50": SpiCS(),
        "mcp3550-60": SpiCS(),
        "mcp3551": SpiCS(),
        "mcp3553": SpiCS(),
    },
    name={
        "vref": NodeName(),
    },
)


@contextlib.contextmanager
def sysfs_trigger() -> Iterator:
    write_int(Path("/sys/bus/iio/devices/iio_sysfs_trigger/add_trigger"), 1)
    try:
        yield
    finally:
        write_int(Path("/sys/bus/iio/devices/iio_sysfs_trigger/remove_trigger"), 1)


@contextlib.contextmanager
def buffer_enable(dev: IIODevice) -> Iterator:
    write_int(dev.path / "buffer0/enable", 1)
    try:
        yield
    finally:
        write_int(dev.path / "buffer0/enable", 0)


@pytest.mark.parametrize(
    "model,node,numchans,maxval",
    [
        (MCP3002, "mcp3002", 4, 0x3FF),
        (MCP3004, "mcp3004", 8, 0x3FF),
        (MCP3008, "mcp3008", 16, 0x3FF),
        (MCP3202, "mcp3202", 4, 0xFFF),
        (MCP3204, "mcp3204", 8, 0xFFF),
        (MCP3208, "mcp3208", 16, 0xFFF),
    ],
    scope="class",
)
class TestMultiChannel:
    @pytest.fixture(scope="class")
    def hw(self, model) -> Iterator:
        with SPIHardware(model) as hw:
            yield hw

    @pytest.fixture(scope="class")
    def dev(self, node) -> Iterator:
        with SPIDriver("mcp320x").bind(dts.spi[node]) as dev:
            yield IIODevice(dev.path)

    def chan_name(self, chan: int, numchans: int) -> str:
        if chan < numchans // 2:
            return f"voltage{chan}"
        else:
            chan -= numchans // 2
            if chan & 1:
                other = chan - 1
            else:
                other = chan + 1

            return f"voltage{chan}-voltage{other}"

    @pytest.fixture(scope="class")
    def channames(self, numchans) -> Sequence[str]:
        return list(self.chan_name(c, numchans) for c in range(numchans))

    @pytest.fixture(scope="class")
    def values(self, maxval, numchans) -> Sequence[int]:
        return [maxval] + list(range(0, maxval, maxval // (numchans * 2)))[
            : numchans - 1
        ]

    @flaky_bus
    def test_raw(self, hw, dev, values, numchans) -> None:
        for chan in range(numchans):
            value = random.choice(values)
            hw.model.set_value(chan, value)
            assert (
                read_int(dev.path / f"in_{self.chan_name(chan, numchans)}_raw") == value
            )

    @flaky_bus
    def test_triggered(
        self,
        hw: SPIHardware[MCP3008],
        dev: IIODevice,
        channames: Sequence[str],
        values: Sequence[int],
        numchans: int,
    ) -> None:
        for channels in [
            list(range(0, numchans, 2)),
            (numchans - 1,),
            list(range(numchans)),
        ]:
            thisvalues = random.choices(values, k=len(channels))
            for i, chan in enumerate(channels):
                hw.model.set_value(chan, thisvalues[i])

            with sysfs_trigger():
                for chan in range(numchans):
                    write_int(dev.path / f"buffer0/in_{channames[chan]}_en", 0)
                for chan in channels:
                    write_int(dev.path / f"buffer0/in_{channames[chan]}_en", 1)
                write_str(dev.path / "trigger/current_trigger", "sysfstrig1")

                with iio.IIOBuffer("/dev/iio:device0", bufidx=0) as buffer:
                    write_int(dev.path / "buffer0/length", 128)

                    with buffer_enable(dev):
                        write_int(dev.path / "buffer0/enable", 1)

                        for i in range(1):
                            write_int(
                                Path(
                                    "/sys/bus/iio/devices/iio_sysfs_trigger/trigger0/trigger_now"
                                ),
                                0,
                            )

                            if hw.fault_injecting:
                                # We can't call read() since it may hang, but do some I/O to
                                # give the IRQ thread a chance to run.
                                hw.kick()
                                continue

                            scanline = buffer.read("<" + "i" * len(channels))
                            assert scanline == tuple(thisvalues)


# Figure 5-1.
MCP3550_50_VALUES: Final = [
    (0x600001, 2097153),
    (0x600000, 2097152),
    (0x1FFFFF, 2097151),
    (0x000002, 2),
    (0x000001, 1),
    (0x000000, 0),
    (0x3FFFFF, -1),
    (0x3FFFFE, -2),
    (0x200000, -2097152),
    (0x9FFFFF, -2097153),
    (0x9FFFFE, -2097154),
]


@pytest.mark.parametrize(
    "model,node,values",
    [
        (MCP3001, "mcp3001", [(0x3FF, 0x3FF)]),
        (MCP3201, "mcp3201", [(0xFFF, 0xFFF)]),
        (
            MCP3301,
            "mcp3301",
            [
                # Table 6-1
                (0b0_1111_1111_1111, +4095),
                (0b0_1111_1111_1110, +4094),
                (0b0_0000_0000_0010, +2),
                (0b0_0000_0000_0001, +1),
                (0b0_0000_0000_0000, 0),
                (0b1_1111_1111_1111, -1),
                (0b1_1111_1111_1110, -2),
                (0b1_0000_0000_0001, -4095),
                (0b1_0000_0000_0000, -4096),
            ],
        ),
        (MCP3550_50, "mcp3550-50", MCP3550_50_VALUES),
        (MCP3550_60, "mcp3550-60", MCP3550_50_VALUES),
        (MCP3551, "mcp3551", MCP3550_50_VALUES),
        (MCP3553, "mcp3553", MCP3550_50_VALUES),
    ],
    scope="class",
)
class TestSingleChannel:
    @pytest.fixture(scope="class")
    def hw(self, model) -> Iterator:
        with SPIHardware(model) as hw:
            yield hw

    @pytest.fixture(scope="class")
    def dev(self, node) -> Iterator:
        with SPIDriver("mcp320x").bind(dts.spi[node]) as dev:
            yield IIODevice(dev.path)

    @flaky_bus
    def test_raw(self, hw, dev, values) -> None:
        for hex, voltage in values:
            hw.model.set_value(hex)
            assert read_int(dev.path / "in_voltage0-voltage1_raw") == voltage

    @flaky_bus
    def test_triggered(self, hw: SPIHardware[MCP3553], dev: IIODevice, values) -> None:
        with sysfs_trigger():
            write_int(dev.path / "buffer0/in_voltage0-voltage1_en", 1)
            write_str(dev.path / "trigger/current_trigger", "sysfstrig1")

            with iio.IIOBuffer("/dev/iio:device0", bufidx=0) as buffer:
                write_int(dev.path / "buffer0/length", 128)

                with buffer_enable(dev):
                    write_int(dev.path / "buffer0/enable", 1)

                    for hex, voltage in values:
                        hw.model.set_value(hex)
                        write_int(
                            Path(
                                "/sys/bus/iio/devices/iio_sysfs_trigger/trigger0/trigger_now"
                            ),
                            0,
                        )

                        if hw.fault_injecting:
                            # We can't call read() since it may hang, but do some I/O to
                            # give the IRQ thread a chance to run.
                            hw.kick()
                            continue

                        scanline = buffer.read("<i")
                        assert scanline[0] == voltage


# Only bother testing one variant which doesn't need init
@pytest.mark.parametrize(
    "model,node,needinit",
    [
        (MCP3301, "mcp3301", False),
        (MCP3550_50, "mcp3550-50", True),
        (MCP3550_60, "mcp3550-60", True),
        (MCP3551, "mcp3551", True),
        (MCP3553, "mcp3553", True),
    ],
    scope="class",
)
class TestInit:
    @pytest.fixture(scope="class")
    def hw(self, model) -> Iterator:
        with SPIHardware(model) as hw:
            yield hw

    @pytest.fixture(scope="class")
    def dev(self, node) -> Iterator:
        with SPIDriver("mcp320x").bind(dts.spi[node]) as dev:
            yield IIODevice(dev.path)

    @flaky_bus
    def test_init(self, hw, dev, needinit) -> None:
        assert hw.update_mock().xfer.call_count == (2 if needinit else 0)
