# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from typing import Any, Final

from roadtest.backend.i2c import SimpleSMBusModel
from roadtest.core.devicetree import DtFragment, I2CAddr, NodeName
from roadtest.core.hardware import HwMock
from roadtest.tests.regulator import bind, voltage_test

REG_VOUT1: Final = 0x01
REG_VOUT2: Final = 0x02
REG_CONTROL: Final = 0x03
REG_STATUS: Final = 0x05


class TPS62864(SimpleSMBusModel):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            # From datasheet section 8.6 Register map
            # XXX does not match reality -- recheck
            regs={
                REG_VOUT1: 0x64,
                REG_VOUT2: 0x64,
                REG_CONTROL: 0x00,
                REG_STATUS: 0x00,
            },
            regbytes=1,
            **kwargs,
        )


dts = DtFragment(
    src="""
#include <dt-bindings/regulator/ti,tps62864.h>

&i2c {
    regulator@$normal$ {
        compatible = "ti,tps62864";
        reg = <0x$normal$>;

        regulators {
            tps62864_normal: SW {
                regulator-name = "+0.85V";
                regulator-min-microvolt = <400000>;
                regulator-max-microvolt = <1675000>;
                regulator-allowed-modes = <TPS62864_MODE_NORMAL TPS62864_MODE_FPWM>;
            };
        };
    };

    regulator@$fpwm$ {
        compatible = "ti,tps62864";
        reg = <0x$fpwm$>;

        regulators {
            tps62864_fpwm: SW {
                regulator-name = "+0.85V";
                regulator-min-microvolt = <400000>;
                regulator-max-microvolt = <1675000>;
                regulator-initial-mode = <TPS62864_MODE_FPWM>;
            };
        };
    };
};

/ {
    $normal-consumer$ {
        compatible = "regulator-virtual-consumer";
        default-supply = <&tps62864_normal>;
    };

    $fpwm-consumer$ {
        compatible = "regulator-virtual-consumer";
        default-supply = <&tps62864_fpwm>;
    };
};
        """,
    i2c={
        "normal": I2CAddr(),
        "fpwm": I2CAddr(),
    },
    name={
        "normal-consumer": NodeName(),
        "fpwm-consumer": NodeName(),
    },
)


def assert_enable(mock: HwMock) -> None:
    mock.assert_last_reg_set_mask(REG_CONTROL, 1 << 5)


def assert_disable(mock: HwMock) -> None:
    mock.assert_last_reg_clear_mask(REG_CONTROL, 1 << 5)


def assert_voltage(mock: HwMock, microvolts: int) -> None:
    val = (microvolts - 400 * 1000) // 5000
    mock.assert_last_reg_write(REG_VOUT1, val)


def assert_mode_normal(mock: HwMock) -> None:
    mock.assert_last_reg_clear_mask(REG_CONTROL, 1 << 4)


def assert_mode_fast(mock: HwMock) -> None:
    mock.assert_last_reg_set_mask(REG_CONTROL, 1 << 4)


def test_voltage() -> None:
    with bind(dts, TPS62864, "tps6286x", "normal") as (hw, regs, consumer):
        voltage_test(
            hw,
            next(regs),
            consumer,
            ranges=[
                range(400_000, 1_675_000 + 1, 5000),
            ],
            assert_enable=assert_enable,
            assert_disable=assert_disable,
            assert_voltage=assert_voltage,
        )


def test_modes() -> None:
    with bind(dts, TPS62864, "tps6286x", "normal") as (hw, _, consumer):
        consumer.mode = "fast"
        assert_mode_fast(hw.update_mock())

        consumer.mode = "normal"
        assert_mode_normal(hw.update_mock())


def test_dt_force_pwm() -> None:
    with bind(dts, TPS62864, "tps6286x", "fpwm") as (hw, _, consumer):
        assert consumer.mode == "fast"
        assert_mode_fast(hw.update_mock())
