# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import errno
from pathlib import Path
from typing import Any, Final, Iterator

import pytest

from roadtest.backend.i2c import SMBusModel
from roadtest.core.devicetree import DtFragment, I2CAddr, NodeName
from roadtest.core.hardware import I2CHardware
from roadtest.support.sysfs import I2CDriver, write_float
from roadtest.tests.iio.iio import IIODevice

REG_MSB: Final = 0x00
REG_LSB: Final = 0x01
REG_CONFIGURATION: Final = 0x0A
REG_DEVICE_ID: Final = 0x11


class OPT4001(SMBusModel):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(regbytes=2, byteorder="big", **kwargs)
        # Reset values from datasheet
        self.regs = {
            REG_MSB: 0x0000,
            REG_LSB: 0x0000,
            REG_CONFIGURATION: 0x3208,
            REG_DEVICE_ID: 0x121,
        }

    def reg_read(self, addr: int) -> int:
        val = self.regs[addr]
        return val

    def reg_write(self, addr: int, val: int) -> None:
        assert addr in self.regs
        self.regs[addr] = val


dts = DtFragment(
    src="""
&i2c {
light-sensor@$addr$ {
    compatible = "ti,opt4001-picostar";
    reg = <0x$addr$>;
    vdd-supply = <&$vdd$>;
};
};
/ {
    $vdd$: $vdd$ {
                compatible = "regulator-fixed";
                regulator-name = "vmmc";
                regulator-min-microvolt = <3300000>;
                regulator-max-microvolt = <3300000>;
    };
};

    """,
    i2c={
        "addr": I2CAddr(),
    },
    name={
        "vdd": NodeName(),
    },
)


@pytest.fixture(scope="module")
def hw() -> Iterator:
    with I2CHardware(OPT4001) as hw:
        yield hw


@pytest.fixture(scope="module")
def dev() -> Iterator:
    with I2CDriver("opt4001").bind(dts.i2c["addr"]) as dev:
        yield IIODevice(dev.path)


@pytest.mark.parametrize(
    "msbval,lsbval,lux",
    [
        (0b_0000_0000_0000_0000, 0b_0000_0000_0000_0000, 0),
        (0b_0000_0000_0000_0000, 0b_0000_0001_0000_0001, 0.0003125),
        (0b_0010_0101_1110_0000, 0b_0000_0000_1001_0000, 481.28),
        (0b_0111_0100_1011_0000, 0b_0000_0000_1111_0011, 12288.0),
        (0b_1111_1111_1111_1111, 0b_1111_1111_1111_1100, 10737408),
    ],
)
def test_illuminance(
    hw: I2CHardware[OPT4001], dev: IIODevice, msbval: int, lsbval: int, lux: float
) -> None:
    hw.model.reg_write(REG_MSB, msbval)
    hw.model.reg_write(REG_LSB, lsbval)
    assert float(dev.in_illuminance_input) == lux


@pytest.mark.parametrize(
    "inttime,regval",
    [
        (0.0006, 0),
        (0.0065, 4),
        (0.8000, 11),
    ],
)
def test_inttime(
    hw: I2CHardware[OPT4001], dev: IIODevice, inttime: float, regval: int
) -> None:
    hw.update_mock().reset_mock()
    write_float(Path("/sys/bus/iio/devices/iio:device0/integration_time"), inttime)
    hw.update_mock().assert_last_reg_write_mask(
        REG_CONFIGURATION, mask=0x1C0, value=(regval << 6)
    )


@pytest.mark.parametrize(
    "msbval,lsbval",
    [
        (0b_0010_0101_1110_0000, 0b_0000_0000_1101_1010),
    ],
)
def test_crc_error(
    hw: I2CHardware[OPT4001], dev: IIODevice, msbval: int, lsbval: int
) -> None:
    hw.model.reg_write(REG_MSB, msbval)
    hw.model.reg_write(REG_LSB, lsbval)
    with pytest.raises(OSError) as ex:
        dev.in_illuminance_input
    assert ex.value.errno == errno.EIO
