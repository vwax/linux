# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import logging
from typing import Any, Final

from roadtest.backend.i2c import SMBusModel
from roadtest.core.devicetree import DtFragment, I2CAddr, NodeName
from roadtest.core.hardware import HwMock, I2CHardware
from roadtest.support.sysfs import I2CDriver, read_int
from roadtest.tests.regulator import bind, voltage_test

logger = logging.getLogger(__name__)

REG_VSET: Final = 0x00
REG_CONTROL1: Final = 0x01
REG_CONTROL2: Final = 0x02
REG_CONTROL3: Final = 0x03
REG_STATUS: Final = 0x04

REG_VSET_RESET: Final = 0x46
REG_CONTROL1_RESET: Final = 0x2A
REG_CONTROL1_SWEN: Final = 0x20
REG_CONTROL1_SWEN_MASK: Final = 0x20
REG_CONTROL1_FPWMEN: Final = 0x10
REG_CONTROL1_FPWMEN_MASK: Final = 0x10
REG_CONTROL1_VRAMP0: Final = 0x00
REG_CONTROL1_VRAMP1: Final = 0x01
REG_CONTROL1_VRAMP2: Final = 0x02
REG_CONTROL1_VRAMP3: Final = 0x03
REG_CONTROL1_VRAMP_MASK: Final = 0x03
REG_CONTROL2_RESET: Final = 0x09
REG_CONTROL2_VRANGE0: Final = 0x00
REG_CONTROL2_VRANGE1: Final = 0x04
REG_CONTROL2_VRANGE2: Final = 0x08
REG_CONTROL2_VRANGE3: Final = 0x0C
REG_CONTROL2_VRANGE_MASK: Final = 0x0C
REG_CONTROL3_RESET: Final = 0x00
REG_STATUS_RESET: Final = 0x02


class TPS62870(SMBusModel):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(regbytes=1, **kwargs)
        self.regs = {
            REG_VSET: REG_VSET_RESET,
            REG_CONTROL1: REG_CONTROL1_RESET & ~REG_CONTROL1_SWEN,
            REG_CONTROL2: REG_CONTROL2_RESET,
            REG_CONTROL3: REG_CONTROL3_RESET,
            REG_STATUS: REG_STATUS_RESET,
        }

    def reg_read(self, addr: int) -> int:
        val = self.regs[addr]
        logger.debug(f"Read {addr=:#02x} {val=:#02x}")
        return val

    def reg_write(self, addr: int, val: int) -> None:
        assert addr in self.regs
        logger.debug(f"Write {addr=:#02x} {val=:#02x}")
        self.regs[addr] = val


dts = DtFragment(
    src="""

&i2c {
    tps62870_vrange0: regulator@$vrange0$ {
        compatible = "ti,tps62870";
        reg = <0x$vrange0$>;

        regulator-name = "v0_4";
        regulator-min-microvolt = <400000>;
        regulator-max-microvolt = <718750>;
        regulator-ramp-delay = <10000>;
        regulator-allowed-modes = <2 1>;
    };

    tps62871_vrange1: regulator@$vrange1$ {
        compatible = "ti,tps62871";
        reg = <0x$vrange1$>;

        regulator-name = "v0_8";
        regulator-min-microvolt = <800000>;
        regulator-max-microvolt = <1037500>;
        regulator-ramp-delay = <5000>;
    };

    tps62872_vrange2: regulator@$vrange2$ {
        compatible = "ti,tps62872";
        reg = <0x$vrange2$>;

        regulator-name = "v1_1";
        regulator-min-microvolt = <1100000>;
        regulator-max-microvolt = <1675000>;
        regulator-ramp-delay = <1250>;
    };

    tps62873_vrange3: regulator@$vrange3$ {
        compatible = "ti,tps62873";
        reg = <0x$vrange3$>;

        regulator-name = "v1_7";
        regulator-min-microvolt = <1700000>;
        regulator-max-microvolt = <3350000>;
        regulator-ramp-delay = <500>;
    };

    tps62870_fpwm: regulator@$fpwm$ {
        compatible = "ti,tps62870";
        reg = <0x$fpwm$>;

        regulator-name = "v0_75";
        regulator-min-microvolt = <400000>;
        regulator-max-microvolt = <1675000>;
        regulator-initial-mode = <1>;
    };
};

/ {
    $vrange0-consumer$ {
        compatible = "regulator-virtual-consumer";
        default-supply = <&tps62870_vrange0>;
    };

    $vrange1-consumer$ {
        compatible = "regulator-virtual-consumer";
        default-supply = <&tps62871_vrange1>;
    };

    $vrange2-consumer$ {
        compatible = "regulator-virtual-consumer";
        default-supply = <&tps62872_vrange2>;
    };

    $vrange3-consumer$ {
        compatible = "regulator-virtual-consumer";
        default-supply = <&tps62873_vrange3>;
    };

    $fpwm-consumer$ {
        compatible = "regulator-virtual-consumer";
        default-supply = <&tps62870_fpwm>;
    };
};
        """,
    i2c={
        "vrange0": I2CAddr(),
        "vrange1": I2CAddr(),
        "vrange2": I2CAddr(),
        "vrange3": I2CAddr(),
        "fpwm": I2CAddr(),
    },
    name={
        "vrange0-consumer": NodeName(),
        "vrange1-consumer": NodeName(),
        "vrange2-consumer": NodeName(),
        "vrange3-consumer": NodeName(),
        "fpwm-consumer": NodeName(),
    },
)


def check_bits_set(value: int, mask: int, bits: int) -> bool:
    return value & mask == bits & mask


def assert_enable(mock: HwMock) -> None:
    mock.assert_last_reg_set_mask(REG_CONTROL1, REG_CONTROL1_SWEN)


def assert_disable(mock: HwMock) -> None:
    mock.assert_last_reg_clear_mask(REG_CONTROL1, REG_CONTROL1_SWEN)


def assert_voltage_vrange0(mock: HwMock, microvolts: int) -> None:
    val = (microvolts - 400 * 1000) // 1250
    mock.assert_last_reg_write(REG_VSET, val)


def assert_voltage_vrange1(mock: HwMock, microvolts: int) -> None:
    val = (microvolts - 400 * 1000) // 2500
    mock.assert_last_reg_write(REG_VSET, val)


def assert_voltage_vrange2(mock: HwMock, microvolts: int) -> None:
    val = (microvolts - 400 * 1000) // 5000
    mock.assert_last_reg_write(REG_VSET, val)


def assert_voltage_vrange3(mock: HwMock, microvolts: int) -> None:
    val = (microvolts - 800 * 1000) // 10000
    mock.assert_last_reg_write(REG_VSET, val)


def assert_mode_normal(mock: HwMock) -> None:
    mock.assert_last_reg_clear_mask(REG_CONTROL1, REG_CONTROL1_FPWMEN)


def assert_mode_fast(mock: HwMock) -> None:
    mock.assert_last_reg_set_mask(REG_CONTROL1, REG_CONTROL1_FPWMEN)


def test_voltage_vrange0() -> None:
    with bind(dts, TPS62870, "tps6287x", "vrange0") as (hw, regulators, consumer):
        voltage_test(
            hw,
            next(regulators),
            consumer,
            ranges=[
                range(400_000, 718_750 + 1, 1250),
            ],
            assert_enable=assert_enable,
            assert_disable=assert_disable,
            assert_voltage=assert_voltage_vrange0,
        )


def test_voltage_vrange1() -> None:
    with bind(dts, TPS62870, "tps6287x", "vrange1") as (hw, regulators, consumer):
        voltage_test(
            hw,
            next(regulators),
            consumer,
            ranges=[
                range(800_000, 1_037_500 + 1, 2500),
            ],
            assert_enable=assert_enable,
            assert_disable=assert_disable,
            assert_voltage=assert_voltage_vrange1,
        )


def test_voltage_vrange2() -> None:
    with bind(dts, TPS62870, "tps6287x", "vrange2") as (hw, regulators, consumer):
        voltage_test(
            hw,
            next(regulators),
            consumer,
            ranges=[
                range(1_100_000, 1_675_000 + 1, 5000),
            ],
            assert_enable=assert_enable,
            assert_disable=assert_disable,
            assert_voltage=assert_voltage_vrange2,
        )


def test_voltage_vrange3() -> None:
    with bind(dts, TPS62870, "tps6287x", "vrange3") as (hw, regulators, consumer):
        voltage_test(
            hw,
            next(regulators),
            consumer,
            ranges=[
                range(1_700_000, 3_350_000 + 1, 10000),
            ],
            assert_enable=assert_enable,
            assert_disable=assert_disable,
            assert_voltage=assert_voltage_vrange3,
        )


def test_get_voltage_vrange0() -> None:
    with (I2CHardware(TPS62870), I2CDriver("tps6287x").bind(dts.i2c["vrange0"]) as dev):
        microvolts = list(dev.path.glob("*regulator/*/microvolts"))[0]
        assert read_int(dev.path / microvolts) == 718750


def test_get_voltage_vrange1() -> None:
    with (I2CHardware(TPS62870), I2CDriver("tps6287x").bind(dts.i2c["vrange1"]) as dev):
        microvolts = list(dev.path.glob("*regulator/*/microvolts"))[0]
        assert read_int(dev.path / microvolts) == 800000


def test_get_voltage_vrange2() -> None:
    with (I2CHardware(TPS62870), I2CDriver("tps6287x").bind(dts.i2c["vrange2"]) as dev):
        microvolts = list(dev.path.glob("*regulator/*/microvolts"))[0]
        assert read_int(dev.path / microvolts) == 1100000


def test_get_voltage_vrange3() -> None:
    with (I2CHardware(TPS62870), I2CDriver("tps6287x").bind(dts.i2c["vrange3"]) as dev):
        microvolts = list(dev.path.glob("*regulator/*/microvolts"))[0]
        assert read_int(dev.path / microvolts) == 1700000


def test_vramp0() -> None:
    with (I2CHardware(TPS62870) as hw, I2CDriver("tps6287x").bind(dts.i2c["vrange0"])):
        val = hw.update_mock().get_last_reg_write(REG_CONTROL1)
        assert check_bits_set(val, REG_CONTROL1_VRAMP_MASK, REG_CONTROL1_VRAMP0)


def test_vramp1() -> None:
    with (I2CHardware(TPS62870) as hw, I2CDriver("tps6287x").bind(dts.i2c["vrange1"])):
        val = hw.update_mock().get_last_reg_write(REG_CONTROL1)
        assert check_bits_set(val, REG_CONTROL1_VRAMP_MASK, REG_CONTROL1_VRAMP1)


def test_vramp2() -> None:
    with (I2CHardware(TPS62870), I2CDriver("tps6287x").bind(dts.i2c["vrange2"])):
        # vrange2 is default, thus driver does not update control1 vramp field
        pass


def test_vramp3() -> None:
    with (I2CHardware(TPS62870) as hw, I2CDriver("tps6287x").bind(dts.i2c["vrange3"])):
        val = hw.update_mock().get_last_reg_write(REG_CONTROL1)
        assert check_bits_set(val, REG_CONTROL1_VRAMP_MASK, REG_CONTROL1_VRAMP3)


def test_vrange0() -> None:
    with (I2CHardware(TPS62870) as hw, I2CDriver("tps6287x").bind(dts.i2c["vrange0"])):
        val = hw.update_mock().get_last_reg_write(REG_CONTROL2)
        assert check_bits_set(val, REG_CONTROL2_VRANGE_MASK, REG_CONTROL2_VRANGE0)


def test_vrange1() -> None:
    with (I2CHardware(TPS62870) as hw, I2CDriver("tps6287x").bind(dts.i2c["vrange1"])):
        val = hw.update_mock().get_last_reg_write(REG_CONTROL2)
        assert check_bits_set(val, REG_CONTROL2_VRANGE_MASK, REG_CONTROL2_VRANGE1)


def test_vrange2() -> None:
    with (I2CHardware(TPS62870), I2CDriver("tps6287x").bind(dts.i2c["vrange2"])):
        # vrange2 is default, thus driver does not update control2 vrange field
        pass


def test_vrange3() -> None:
    with (I2CHardware(TPS62870) as hw, I2CDriver("tps6287x").bind(dts.i2c["vrange3"])):
        val = hw.update_mock().get_last_reg_write(REG_CONTROL2)
        assert check_bits_set(val, REG_CONTROL2_VRANGE_MASK, REG_CONTROL2_VRANGE3)


def test_fpwm() -> None:
    with (I2CHardware(TPS62870) as hw, I2CDriver("tps6287x").bind(dts.i2c["fpwm"])):
        val = hw.update_mock().get_last_reg_write(REG_CONTROL1)
        assert check_bits_set(val, REG_CONTROL1_FPWMEN_MASK, REG_CONTROL1_FPWMEN)


def test_modes() -> None:
    with bind(dts, TPS62870, "tps6287x", "vrange0") as (hw, _, consumer):
        consumer.mode = "fast"
        assert_mode_fast(hw.update_mock())
        consumer.mode = "normal"
        assert_mode_normal(hw.update_mock())


def test_dt_force_pwm() -> None:
    with bind(dts, TPS62870, "tps6287x", "fpwm") as (hw, _, consumer):
        assert consumer.mode == "fast"
        assert_mode_fast(hw.update_mock())
