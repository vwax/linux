# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import contextlib
import logging
from pathlib import Path
from typing import Any, Iterator, Sequence

import pytest

from roadtest.backend.spi import WordSPIModel
from roadtest.core.devicetree import DtFragment, NodeName, SpiCS
from roadtest.core.hardware import SPIHardware
from roadtest.core.suite import flaky_bus
from roadtest.support.sysfs import SPIDriver, read_int, write_int, write_str
from roadtest.tests.iio import iio
from roadtest.tests.iio.iio import IIODevice

logger = logging.getLogger(__name__)


class ADC084S021(WordSPIModel):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(wordbytes=2, byteorder="big", **kwargs)
        self.values: tuple[int, int, int, int] = (0, 0, 0, 0)

    def word_xfer(self, inwords: Sequence[int]) -> Sequence[int]:
        logger.debug(f"{inwords=}")

        outwords = [0] + [self.values[word >> (8 + 3)] << 4 for word in inwords[:-1]]
        logger.debug(f"{outwords=}")
        return outwords


dts = DtFragment(
    src="""
&spi {
    foo@$cs$ {
        compatible = "ti,adc084s021";
        reg = <0x$cs$>;
        vref-supply = <&$vref$>;
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
        "cs": SpiCS(),
    },
    name={
        "vref": NodeName(),
    },
)


@pytest.fixture(scope="module")
def hw() -> Iterator:
    with SPIHardware(ADC084S021) as hw:
        yield hw


@pytest.fixture(scope="module")
def dev() -> Iterator:
    with SPIDriver("adc084s021").bind(dts.spi["cs"]) as dev:
        yield IIODevice(dev.path)


@flaky_bus
def test_illuminance(hw: SPIHardware[ADC084S021], dev: IIODevice) -> None:
    values = (10, 20, 30, 40)
    hw.model.values = values

    for chan, value in enumerate(values):
        raw = dev.path / f"in_voltage{chan}_raw"
        assert read_int(raw) == value


def test_scale(hw: SPIHardware[ADC084S021], dev: IIODevice) -> None:
    assert int(dev.in_voltage_scale) == 3300


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


@flaky_bus
def test_proximity_triggered(hw: SPIHardware[ADC084S021], dev: IIODevice) -> None:
    hw.model.values = (10, 20, 30, 40)

    with sysfs_trigger():
        write_int(dev.path / "buffer0/in_voltage1_en", 1)
        write_int(dev.path / "buffer0/in_voltage3_en", 1)
        write_str(dev.path / "trigger/current_trigger", "sysfstrig1")

        with iio.IIOBuffer("/dev/iio:device0", bufidx=0) as buffer:
            write_int(dev.path / "buffer0/length", 128)

            with buffer_enable(dev):
                for i in range(2):
                    write_int(
                        Path(
                            "/sys/bus/iio/devices/iio_sysfs_trigger/trigger0/trigger_now"
                        ),
                        0,
                    )

                    if hw.fault_injecting:
                        # When fault injecting, the buffer.read() could hang,
                        # so we can't wait for that.  But we do want to give
                        # the IRQ thread a chance to run and try to talk to
                        # the device, so just make this process do some
                        # I/O by kicking the hardware.
                        hw.kick()
                        continue

                    scanline = buffer.read(">HH")

                    val = (scanline[0] >> 4) & 0xFF
                    assert val == 20

                    val = (scanline[1] >> 4) & 0xFF
                    assert val == 40

                    # hw.model.set_values((1, 2, 3, 4))
