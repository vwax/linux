# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from typing import Any, Final

from roadtest.backend.i2c import SimpleSMBusModel
from roadtest.core.devicetree import DtFragment, DtVar
from roadtest.core.hardware import Hardware
from roadtest.core.modules import insmod, rmmod
from roadtest.core.suite import UMLTestCase
from roadtest.core.sysfs import (
    I2CDriver,
    PlatformDriver,
    read_str,
    write_int,
    write_str,
)

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


class TestTPS62864(UMLTestCase):
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
    tps62864_normal_consumer {
        compatible = "regulator-virtual-consumer";
        default-supply = <&tps62864_normal>;
    };

    tps62864_fpwm_consumer {
        compatible = "regulator-virtual-consumer";
        default-supply = <&tps62864_fpwm>;
    };
};
        """,
        variables={
            "normal": DtVar.I2C_ADDR,
            "fpwm": DtVar.I2C_ADDR,
        },
    )

    @classmethod
    def setUpClass(cls) -> None:
        insmod("tps6286x-regulator")

    @classmethod
    def tearDownClass(cls) -> None:
        rmmod("tps6286x-regulator")

    def setUp(self) -> None:
        self.driver = I2CDriver("tps6286x")
        self.hw = Hardware("i2c")
        self.hw.load_model(TPS62864)

    def tearDown(self) -> None:
        self.hw.close()

    def test_voltage(self) -> None:
        with (
            self.driver.bind(self.dts["normal"]),
            PlatformDriver("reg-virt-consumer").bind(
                "tps62864_normal_consumer"
            ) as consumerdev,
        ):
            maxfile = consumerdev.path / "max_microvolts"
            minfile = consumerdev.path / "min_microvolts"

            write_int(maxfile, 1675000)
            write_int(minfile, 800000)

            mock = self.hw.update_mock()
            mock.assert_reg_write_once(self, REG_CONTROL, 1 << 5)
            mock.assert_reg_write_once(self, REG_VOUT1, 0x50)
            mock.reset_mock()

            mV = 1000
            data = [
                (400 * mV, 0x00),
                (900 * mV, 0x64),
                (1675 * mV, 0xFF),
            ]

            for voltage, val in data:
                write_int(minfile, voltage)
                mock = self.hw.update_mock()
                mock.assert_reg_write_once(self, REG_VOUT1, val)
                mock.reset_mock()

            write_int(minfile, 0)
            mock = self.hw.update_mock()
            mock.assert_reg_write_once(self, REG_CONTROL, 0)
            mock.reset_mock()

    def test_modes(self) -> None:
        with (
            self.driver.bind(self.dts["normal"]),
            PlatformDriver("reg-virt-consumer").bind(
                "tps62864_normal_consumer"
            ) as consumerdev,
        ):
            modefile = consumerdev.path / "mode"
            write_str(modefile, "fast")

            mock = self.hw.update_mock()
            mock.assert_reg_write_once(self, REG_CONTROL, 1 << 4)
            mock.reset_mock()

            write_str(modefile, "normal")
            mock = self.hw.update_mock()
            mock.assert_reg_write_once(self, REG_CONTROL, 0)
            mock.reset_mock()

    def test_dt_force_pwm(self) -> None:
        with (
            self.driver.bind(self.dts["fpwm"]),
            PlatformDriver("reg-virt-consumer").bind(
                "tps62864_fpwm_consumer"
            ) as consumerdev,
        ):
            mock = self.hw.update_mock()
            mock.assert_reg_write_once(self, REG_CONTROL, 1 << 4)
            mock.reset_mock()

            modefile = consumerdev.path / "mode"
            self.assertEquals(read_str(modefile), "fast")

            maxfile = consumerdev.path / "max_microvolts"
            minfile = consumerdev.path / "min_microvolts"

            write_int(maxfile, 1675000)
            write_int(minfile, 800000)

            mock = self.hw.update_mock()
            mock.assert_reg_write_once(self, REG_CONTROL, 1 << 5 | 1 << 4)
            mock.reset_mock()
