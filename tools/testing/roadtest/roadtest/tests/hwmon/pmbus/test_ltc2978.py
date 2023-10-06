# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import logging
from pathlib import Path
from typing import Any, Final

from roadtest.backend.i2c import I2CModel
from roadtest.core.devicetree import DtFragment, I2CAddr
from roadtest.core.hardware import I2CHardware
from roadtest.support.sysfs import I2CDriver, read_int

logger = logging.getLogger(__name__)

CRC_POLYNOM = 0x1070 << 3
VOUT_COMMAND_INIT = 0xA000

PMBUS_PAGE: Final = 0x00
PMBUS_OPERATION: Final = 0x01
PMBUS_WRITE_PROTECT: Final = 0x10
PMBUS_CAPABILITY: Final = 0x19
PMBUS_VOUT_MODE: Final = 0x20
PMBUS_VOUT_COMMAND: Final = 0x21
PMBUS_VOUT_OV_FAULT_LIMIT: Final = 0x40
PMBUS_VOUT_OV_WARN_LIMIT: Final = 0x42
PMBUS_VOUT_UV_WARN_LIMIT: Final = 0x43
PMBUS_VOUT_UV_FAULT_LIMIT: Final = 0x44
PMBUS_OT_FAULT_LIMIT: Final = 0x4F
PMBUS_OT_WARN_LIMIT: Final = 0x51
PMBUS_UT_WARN_LIMIT: Final = 0x52
PMBUS_UT_FAULT_LIMIT: Final = 0x53
PMBUS_VIN_OV_FAULT_LIMIT: Final = 0x55
PMBUS_VIN_OV_FAULT_RESPONSE: Final = 0x56
PMBUS_VIN_OV_WARN_LIMIT: Final = 0x57
PMBUS_VIN_UV_WARN_LIMIT: Final = 0x58
PMBUS_VIN_UV_FAULT_LIMIT: Final = 0x59
PMBUS_STATUS_WORD: Final = 0x79
PMBUS_STATUS_VOUT: Final = 0x7A
PMBUS_STATUS_INPUT: Final = 0x7C
PMBUS_STATUS_TEMPERATURE: Final = 0x7D
PMBUS_STATUS_CML: Final = 0x7E
PMBUS_STATUS_OTHER: Final = 0x7F
PMBUS_STATUS_MFR_SPECIFIC: Final = 0x80
PMBUS_READ_VIN: Final = 0x88
PMBUS_READ_VOUT: Final = 0x8B
PMBUS_MFR_VIN_MIN: Final = 0xA0
PMBUS_MFR_VIN_MAX: Final = 0xA1
PMBUS_MFR_IIN_MAX: Final = 0xA2
PMBUS_MFR_PIN_MAX: Final = 0xA3
PMBUS_MFR_VOUT_MIN: Final = 0xA4
PMBUS_MFR_VOUT_MAX: Final = 0xA5
PMBUS_MFR_IOUT_MAX: Final = 0xA6
PMBUS_MFR_POUT_MAX: Final = 0xA7
PMBUS_MFR_MAX_TEMP_1: Final = 0xC0
LTC2978_MFR_VOUT_PEAK: Final = 0xDD
LTC2978_MFR_VIN_PEAK: Final = 0xDE
LTC2978_MFR_TEMPERATURE_PEAK: Final = 0xDF
LTC2978_MFR_SPECIAL_ID: Final = 0xE7
LTC2978_MFR_COMMON: Final = 0xEF
LTC2978_MFR_VOUT_MIN: Final = 0xFB
LTC2978_MFR_VIN_MIN: Final = 0xFC
LTC2978_MFR_TEMPERATURE_MIN: Final = 0xFD


class LTC2978(I2CModel):
    def __init__(
        self,
        i2c_addr: int,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.i2c_addr = i2c_addr
        self.reg_addr = 0x0
        self.pec = 0
        self.page = 0

        self.bregs = {
            PMBUS_PAGE: 0x00,
            PMBUS_OPERATION: 0x00,
            PMBUS_WRITE_PROTECT: 0x00,
            PMBUS_CAPABILITY: 0xB0,
            PMBUS_VOUT_MODE: 0x13,
            PMBUS_VIN_OV_FAULT_RESPONSE: 0x80,
            PMBUS_STATUS_VOUT: 0x00,
            PMBUS_STATUS_INPUT: 0x00,
            PMBUS_STATUS_TEMPERATURE: 0x00,
            PMBUS_STATUS_CML: 0x00,
            PMBUS_STATUS_OTHER: 0x00,
            PMBUS_STATUS_MFR_SPECIFIC: 0x00,
        }

        self.wregs = {
            PMBUS_VOUT_COMMAND: 0x2000,
            PMBUS_VOUT_OV_FAULT_LIMIT: 0x2333,
            PMBUS_VOUT_OV_WARN_LIMIT: 0x2266,
            PMBUS_VOUT_UV_WARN_LIMIT: 0x1D9A,
            PMBUS_VOUT_UV_FAULT_LIMIT: 0x1CCD,
            PMBUS_OT_WARN_LIMIT: 0xEA30,
            PMBUS_UT_WARN_LIMIT: 0x8000,
            PMBUS_UT_FAULT_LIMIT: 0xE580,
            PMBUS_OT_FAULT_LIMIT: 0xEB48,
            PMBUS_VIN_OV_FAULT_LIMIT: 0xD3C0,
            PMBUS_VIN_OV_WARN_LIMIT: 0xD380,
            PMBUS_VIN_UV_WARN_LIMIT: 0x8000,
            PMBUS_VIN_UV_FAULT_LIMIT: 0x8000,
            PMBUS_STATUS_WORD: 0x0000,
            PMBUS_READ_VIN: 0xAAAA,
            PMBUS_READ_VOUT: VOUT_COMMAND_INIT,
            PMBUS_MFR_VIN_MIN: 0x0000,
            PMBUS_MFR_VIN_MAX: 0xFFFF,
            PMBUS_MFR_IIN_MAX: 0xFFFF,
            PMBUS_MFR_PIN_MAX: 0xFFFF,
            PMBUS_MFR_VOUT_MIN: 0x0000,
            PMBUS_MFR_VOUT_MAX: 0xFFFF,
            PMBUS_MFR_IOUT_MAX: 0xFFFF,
            PMBUS_MFR_POUT_MAX: 0xFFFF,
            PMBUS_MFR_MAX_TEMP_1: 0xFFFF,
            LTC2978_MFR_VOUT_PEAK: 0xFFFF,
            LTC2978_MFR_VIN_PEAK: 0xFFFF,
            LTC2978_MFR_TEMPERATURE_PEAK: 0xFFFF,
            LTC2978_MFR_SPECIAL_ID: 0x0130,
            LTC2978_MFR_VOUT_MIN: 0x0000,
            LTC2978_MFR_VIN_MIN: 0x0000,
            LTC2978_MFR_TEMPERATURE_MIN: 0x0000,
        }

        self.paged_read_vout_paged = {
            0: VOUT_COMMAND_INIT,
            1: VOUT_COMMAND_INIT,
            2: VOUT_COMMAND_INIT,
            3: VOUT_COMMAND_INIT,
            4: VOUT_COMMAND_INIT,
            5: VOUT_COMMAND_INIT,
            6: VOUT_COMMAND_INIT,
            7: VOUT_COMMAND_INIT,
        }

    def val_to_bytes(self, val: int, length: int) -> bytes:
        return val.to_bytes(length, byteorder="little")

    def breg_write(self, addr: int, val: int) -> None:
        self.bregs[addr] = val
        if addr == PMBUS_PAGE:
            self.page = val

    def wreg_write(self, addr: int, val: int) -> None:
        self.wregs[addr] = val

    def _crc8(self, data: int) -> int:
        for i in range(0, 8):
            if data & 0x8000:
                data = data ^ CRC_POLYNOM
            data = data << 1
        return data >> 8

    def calc_pec(self, crc_orig: int, data: bytes, count: int) -> int:
        crc = crc_orig
        # logger.debug(f"orig crc {crc=:#02x}")

        for i in range(0, count):
            crc = self._crc8((crc ^ data[i]) << 8)
            # logger.debug(f"{data[i]=:#02x} => {crc=:#02x}")
        return crc

    def read(self, length: int) -> bytes:
        data = bytearray()
        wants_pec = 1

        # Word register read
        if self.reg_addr in self.wregs:
            # Specific page handling of PMBUS_READ_VOUT
            # Ideally all paged registers should be page
            # mapped (multidimentional register map)
            if self.reg_addr == PMBUS_READ_VOUT:
                val = self.paged_read_vout_paged[self.page]
            else:
                val = self.wregs[self.reg_addr]
            data += self.val_to_bytes(val, 2)
            if length == 2:
                wants_pec = 0
        # Byte register read
        elif self.reg_addr in self.bregs:
            val = self.bregs[self.reg_addr]
            data += self.val_to_bytes(val, 1)
        else:
            raise Exception(f"Reg {self.reg_addr:#02x} not implemented!")

        # If more than 1 byte requested append PEC as last byte
        if length > 1 and wants_pec == 1:
            self.pec = self.calc_pec(
                self.pec, self.val_to_bytes((self.i2c_addr << 1) + 1, 1), 1
            )
            self.pec = self.calc_pec(self.pec, data, length - 1)
            data += self.pec.to_bytes(1, byteorder="little")
        logger.debug(
            f"Read {self.reg_addr=:#02x} {val=:#04x} {self.pec=:#02x} {length=:d}"
        )
        return bytes(data)

    def write(self, data: bytes) -> None:
        self.reg_addr = data[0]

        # Calculate PEC and save it for last byte on next read reply message
        self.pec = self.calc_pec(0, self.val_to_bytes(self.i2c_addr << 1, 1), 1)
        if len(data) > 1:
            self.pec = data[len(data) - 1]
        else:
            self.pec = self.calc_pec(self.pec, data, len(data))

        length = len(data) - 1
        data = data[1:]

        logger.debug(f"Write {self.reg_addr=:#02x} {length=:d} {self.pec=:#02x}")

        # The only 2 byte data write in this test suite (fake change in READ_VOUT register)
        if self.reg_addr == PMBUS_VOUT_COMMAND:
            self.backend.mock.reg_write(PMBUS_READ_VOUT, data[1] << 8 | data[0])
            self.paged_read_vout_paged[self.page] = data[1] << 8 | data[0]
        # Else only handle 1 byte data writes. In case length is 2 it is PEC which we do not write
        elif length > 0:
            self.backend.mock.reg_write(self.reg_addr, data[0])
            self.breg_write(self.reg_addr, data[0])


dts = DtFragment(
    src="""
&i2c {
    power-monitor@$addr$ {
        compatible = "lltc,ltc2977";
        reg = <0x$addr$>;

        regulators {
            v5_0_1: vout0 {
                regulator-name = "5_0v_1";
                regulator-min-microvolt = <4370000>;
                regulator-max-microvolt = <4483000>;
                regulator-always-on;
            };

            v5_0_2: vout1 {
                regulator-name = "5_0v_2";
                regulator-min-microvolt = <5369000>;
                regulator-max-microvolt = <5483000>;
                regulator-always-on;
            };
        };
    };
};
    """,
    i2c={
        "addr": I2CAddr(),
    },
)

# This tests initiation of the regulator with the get/set_voltage
# regulator ops. The regulator core reads the DT nodes and uses the
# get/set_voltage ops to adjust the regulator channel output voltage
# PMBUS_READ_VOUT to be within the preconfigured range (min/max).
# Initial output voltage value is preset to Linear16 value 0xA000
# (VOUT_COMMAND_INIT) which translates to 5000 mV.
def test_get_set_voltage() -> None:
    with (
        I2CHardware(LTC2978, i2c_addr=dts.i2c["addr"].val),
        I2CDriver("ltc2978").bind(dts.i2c["addr"]) as dev,
    ):
        # Verify that the 'v5_0v_1' channel vout is adjusted from initial
        # 5000mV to be within min/max range. 'sysfs attributes in2*' are
        # mapped to the 'v5_0v_1' channel
        input = Path(f"{dev.path}/hwmon/hwmon0/in2_input")
        val = read_int(input)
        assert val == 4483

        # Verify that the 'v5_0v_2' channel vout is adjusted from initial
        # 5000mV to be within min/max range. 'sysfs attributes in3*' are
        # mapped to the 'v5_0v_2' channel
        input = Path(f"{dev.path}/hwmon/hwmon0/in3_input")
        val = read_int(input)
        assert val == 5369
