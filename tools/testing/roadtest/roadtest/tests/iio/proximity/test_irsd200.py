import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import pytest

from roadtest.backend.i2c import SMBusModel
from roadtest.core.devicetree import DtFragment, GpioPin, I2CAddr
from roadtest.core.hardware import I2CHardware
from roadtest.core.suite import flaky_bus
from roadtest.support.sysfs import (
    I2CDevice,
    I2CDriver,
    read_float,
    read_int,
    read_str,
    write_bool,
    write_float,
    write_int,
    write_str,
)
from roadtest.tests.iio import iio
from roadtest.tests.iio.iio import IIODevice

dts = DtFragment(
    src="""
#include <dt-bindings/interrupt-controller/irq.h>

&i2c {
    pir@$addr$ {
        compatible = "murata,irsd200";
        reg = <0x$addr$>;
        interrupt-parent = <&gpio>;
        interrupts = <$gpio$ IRQ_TYPE_EDGE_RISING>;
    };

    probe@$addr_probe$ {
        compatible = "murata,irsd200";
        reg = <0x$addr_probe$>;
        interrupt-parent = <&gpio>;
        interrupts = <$gpio$ IRQ_TYPE_EDGE_RISING>;
    };
};
    """,
    i2c={
        "addr": I2CAddr(),
        "addr_probe": I2CAddr(),
    },
    gpio={
        "gpio": GpioPin(),
    },
)

# Index in list corresponds to the register value (c.f. datasheet).
SAMPL_FREQS: list[int] = [50, 100]
LP_FILTER_FREQS: list[int] = [10, 7]
HP_FILTER_FREQS: list[float] = [0.3, 0.5]

REG_OP: Final = 0x00
REG_DATA_LO: Final = 0x02
REG_DATA_HI: Final = 0x03
REG_STATUS: Final = 0x04
REG_COUNT: Final = 0x05
REG_DATA_RATE: Final = 0x06
REG_FILTER: Final = 0x07
REG_INTR: Final = 0x09
REG_NR_COUNT: Final = 0x0A
REG_THR_HI: Final = 0x0B
REG_THR_LO: Final = 0x0C
REG_TIMER_LO: Final = 0x0D
REG_TIMER_HI: Final = 0x0E

# Interrupt source register values.
INTR_DATA: int = 1 << 0
INTR_TIMER: int = 1 << 1
INTR_COUNT_THR_AND: int = 1 << 2
INTR_COUNT_THR_OR: int = 1 << 3


class IRSD200(SMBusModel):
    def __init__(self, intr: GpioPin, **kwargs: Any) -> None:
        super().__init__(regbytes=1, **kwargs)
        self.intr = intr
        self.regs = {
            REG_OP: 0x00,
            REG_DATA_LO: 0x00,
            REG_DATA_HI: 0x00,
            REG_STATUS: 0x00,
            REG_COUNT: 0x00,
            REG_DATA_RATE: 0x00,
            REG_FILTER: 0x00,
            REG_INTR: 0x00,
            REG_NR_COUNT: 0x00,
            REG_THR_HI: 0x00,
            REG_THR_LO: 0x00,
            REG_TIMER_LO: 0x00,
            REG_TIMER_HI: 0x00,
        }

    def reg_read(self, addr: int) -> int:
        return self.regs[addr]

    def reg_write(self, addr: int, val: int) -> None:
        assert addr in self.regs
        self.regs[addr] = val

    def gen_irq(self, status: int) -> None:
        self.reg_write(REG_STATUS, status)
        self.backend.gpio.set(self.intr, False)
        self.backend.gpio.set(self.intr, True)


@pytest.fixture(scope="module")
def hw() -> Iterator:
    with I2CHardware(IRSD200, intr=dts.gpio["gpio"]) as hw:
        yield hw


@pytest.fixture(scope="module")
def dev() -> Iterator:
    with I2CDriver("irsd200").bind(dts.i2c["addr"]) as dev:
        yield IIODevice(dev.path)


@flaky_bus
def test_probe(hw: I2CHardware[IRSD200]) -> None:
    with I2CDriver("irsd200").bind(dts.i2c["addr_probe"]):
        hw.update_mock()


def test_operational(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    hw.update_mock().assert_reg_write_once(REG_OP, 0x00)


def test_name(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    assert dev.name == "irsd200"


@flaky_bus
def test_available_sampl_freqs(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    assert all(
        int(f) in SAMPL_FREQS
        for f in dev.in_proximity_sampling_frequency_available.split()
    )


@flaky_bus
def test_available_lp_filter_freqs(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    assert all(
        int(f) in LP_FILTER_FREQS
        for f in dev.in_proximity_filter_low_pass_3db_frequency_available.split()
    )


def test_available_hp_filter_freqs(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    assert all(
        float(f) in HP_FILTER_FREQS
        for f in dev.in_proximity_filter_high_pass_3db_frequency_available.split()
    )


@flaky_bus
def test_read_proximity_raw(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    dev.in_proximity_raw


@flaky_bus
def test_rw_sampl_freq(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    path = dev.path / "in_proximity_sampling_frequency"
    for i, freq in enumerate(SAMPL_FREQS):
        write_int(path, freq)
        hw.update_mock().assert_reg_write_once(REG_DATA_RATE, i)
        assert read_int(path) == freq

    with pytest.raises(OSError, match=r"out of range"):
        write_int(path, 49)

    with pytest.raises(OSError, match=r"out of range"):
        write_int(path, 51)

    with pytest.raises(OSError, match=r"out of range"):
        write_int(path, 101)


@flaky_bus
def test_rw_lp_filter_freq(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    # We need to force regmap field writes in order to assert them...
    write_bool(
        Path(
            "/sys/kernel/debug/regmap/"
            f"{I2CDevice(dts.i2c['addr']).id}/force_write_field"
        ),
        True,
    )
    # ...And reset the other field in the register.
    write_float(
        dev.path / "in_proximity_filter_high_pass_3db_frequency",
        HP_FILTER_FREQS[0],
    )

    hw.update_mock()

    path = dev.path / "in_proximity_filter_low_pass_3db_frequency"
    for i, freq in enumerate(LP_FILTER_FREQS):
        write_int(path, freq)
        hw.update_mock().assert_reg_write_once(REG_FILTER, i << 1)
        assert read_int(path) == freq

    with pytest.raises(OSError, match=r"out of range"):
        write_int(path, 1)

    with pytest.raises(OSError, match=r"out of range"):
        write_int(path, 8)

    with pytest.raises(OSError, match=r"out of range"):
        write_int(path, 11)


@flaky_bus
def test_rw_hp_filter_freq(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    # We need to force regmap field writes in order to assert them.
    write_bool(
        Path(
            "/sys/kernel/debug/regmap/"
            f"{I2CDevice(dts.i2c['addr']).id}/force_write_field"
        ),
        True,
    )
    # ...And reset the other field in the register.
    write_int(
        dev.path / "in_proximity_filter_low_pass_3db_frequency",
        LP_FILTER_FREQS[0],
    )

    hw.update_mock()

    path = dev.path / "in_proximity_filter_high_pass_3db_frequency"
    for i, freq in enumerate(HP_FILTER_FREQS):
        write_float(path, freq)
        hw.update_mock().assert_reg_write_once(REG_FILTER, i << 0)
        assert read_float(path) == freq

    with pytest.raises(OSError, match=r"out of range"):
        write_float(path, 0.2)

    with pytest.raises(OSError, match=r"out of range"):
        write_float(path, 0.4)

    with pytest.raises(OSError, match=r"out of range"):
        write_float(path, 0.6)


@flaky_bus
def test_rw_runningcount(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    path_period = dev.path / "events/in_proximity_thresh_either_runningcount"
    with pytest.raises(OSError, match=r"out of range"):
        write_int(path_period, 0)

    period = 1
    write_int(path_period, period)
    hw.update_mock().assert_reg_write_once(REG_NR_COUNT, period)
    assert read_int(path_period) == period

    # Timeout must be non-zero when value is greater or equal to two.
    path_timeout = dev.path / "events/in_proximity_thresh_either_runningperiod"
    write_float(path_timeout, 0)
    with pytest.raises(OSError, match=r"not permitted"):
        write_int(path_period, 2)

    write_float(path_timeout, 1)
    for period in range(2, 8):
        write_int(path_period, period)
        hw.update_mock().assert_reg_write_once(REG_NR_COUNT, period)
        assert read_int(path_period) == period

    with pytest.raises(OSError, match=r"out of range"):
        write_int(path_period, 8)


@flaky_bus
def test_rw_runningperiod(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    path = dev.path / "events/in_proximity_thresh_either_runningperiod"
    for freq in SAMPL_FREQS:
        write_int(dev.path / "in_proximity_sampling_frequency", freq)
        assert read_int(dev.path / "in_proximity_sampling_frequency") == freq

        hw.update_mock()

        data = [
            (0x00, 0x00),
            (0x00, 0x01),
            (0x01, 0x00),
            (0x02, 0x34),
            (0x03, 0xFF),  # Maximum value.
        ]
        for high, low in data:
            time = ((high << 8) | low) / freq
            write_float(path, time)
            mock = hw.update_mock()
            mock.assert_reg_write_once(REG_TIMER_HI, high)
            mock.assert_reg_write_once(REG_TIMER_LO, low)
            assert read_float(path) == time

        max_val = data[-1][-1]

        with pytest.raises(OSError, match=r"out of range"):
            write_float(path, max_val + 1)

        with pytest.raises(OSError, match=r"out of range"):
            write_float(path, -1)


@flaky_bus
def test_rw_thresh_falling(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    path = dev.path / "events/in_proximity_thresh_falling_value"

    with pytest.raises(OSError, match=r"out of range"):
        write_int(path, 1)

    val = 0
    write_int(path, val)
    hw.update_mock().assert_reg_write_once(REG_THR_LO, val)
    assert read_int(path) == val

    scale = -128
    val = 123 * scale
    write_int(path, val)
    hw.update_mock().assert_reg_write_once(REG_THR_LO, val // scale)
    assert read_int(path) == val

    min_val = -255 * 128
    with pytest.raises(OSError, match=r"out of range"):
        write_int(path, min_val - 128)


@flaky_bus
def test_rw_thresh_rising(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    path = dev.path / "events/in_proximity_thresh_rising_value"

    with pytest.raises(OSError, match=r"out of range"):
        write_int(path, -1)

    val = 0
    write_int(path, 0)
    hw.update_mock().assert_reg_write_once(REG_THR_HI, val)
    assert read_int(path) == val

    scale = 128
    val = 123 * scale
    write_int(path, val)
    hw.update_mock().assert_reg_write_once(REG_THR_HI, val // scale)
    assert read_int(path) == val

    max_val = 255 * 128
    with pytest.raises(OSError, match=r"out of range"):
        write_int(path, max_val + 128)


@contextlib.contextmanager
def sysfs_enable(dev_path: Path) -> Iterator:
    write_int(dev_path, 1)
    try:
        yield
    finally:
        write_int(dev_path, 0)


@flaky_bus
def test_thresh_event_rising(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    path_en = dev.path / "events/in_proximity_thresh_either_en"

    # We need to force regmap field writes in order to assert them.
    write_bool(
        Path(
            "/sys/kernel/debug/regmap/"
            f"{I2CDevice(dts.i2c['addr']).id}/force_write_field"
        ),
        True,
    )
    # ...And reset the other fields in the register.
    write_int(path_en, 0)
    write_int(dev.path / "buffer/enable", 0)

    hw.update_mock()

    with sysfs_enable(path_en):
        hw.update_mock().assert_reg_write_once(REG_INTR, INTR_COUNT_THR_OR)
        assert read_int(path_en) == 1

        with iio.IIOEventMonitor("/dev/iio:device0") as monitor:
            hw.model.reg_write(REG_COUNT, 1 << 4)
            hw.model.gen_irq(INTR_COUNT_THR_OR)
            hw.kick()

            if hw.fault_injecting:
                # When fault injecting, the monitor.read() could hang, so we
                # can't wait for that.
                return

            event = monitor.read()
            assert event.ch_type == iio.IIOChanType.IIO_PROXIMITY
            assert event.type == iio.IIOEventType.IIO_EV_TYPE_THRESH
            assert event.dir == iio.IIOEventDirection.IIO_EV_DIR_RISING


@flaky_bus
def test_thresh_event_falling(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    path_en = dev.path / "events/in_proximity_thresh_either_en"

    # We need to force regmap field writes in order to assert them.
    write_bool(
        Path(
            "/sys/kernel/debug/regmap/"
            f"{I2CDevice(dts.i2c['addr']).id}/force_write_field"
        ),
        True,
    )
    # ...And reset the other fields in the register.
    write_int(path_en, 0)
    write_int(dev.path / "buffer/enable", 0)

    hw.update_mock()

    with sysfs_enable(path_en):
        hw.update_mock().assert_reg_write_once(REG_INTR, INTR_COUNT_THR_OR)
        assert read_int(path_en) == 1

        with iio.IIOEventMonitor("/dev/iio:device0") as monitor:
            hw.model.reg_write(REG_COUNT, 1 << 0)
            hw.model.gen_irq(INTR_COUNT_THR_OR)
            hw.kick()

            if hw.fault_injecting:
                # When fault injecting, the monitor.read() could hang, so we
                # can't wait for that.
                return

            event = monitor.read()
            assert event.ch_type == iio.IIOChanType.IIO_PROXIMITY
            assert event.type == iio.IIOEventType.IIO_EV_TYPE_THRESH
            assert event.dir == iio.IIOEventDirection.IIO_EV_DIR_FALLING


@flaky_bus
def test_thresh_event_either(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    path_en = dev.path / "events/in_proximity_thresh_either_en"

    # We need to force regmap field writes in order to assert them.
    write_bool(
        Path(
            "/sys/kernel/debug/regmap/"
            f"{I2CDevice(dts.i2c['addr']).id}/force_write_field"
        ),
        True,
    )
    # ...And reset the other fields in the register.
    write_int(path_en, 0)
    write_int(dev.path / "buffer/enable", 0)

    hw.update_mock()

    with sysfs_enable(path_en):
        hw.update_mock().assert_reg_write_once(REG_INTR, INTR_COUNT_THR_OR)
        assert read_int(path_en) == 1

        with iio.IIOEventMonitor("/dev/iio:device0") as monitor:
            hw.model.reg_write(REG_COUNT, (1 << 4) | (1 << 0))
            hw.model.gen_irq(INTR_COUNT_THR_OR)
            hw.kick()

            if hw.fault_injecting:
                # When fault injecting, the monitor.read() could hang, so we
                # can't wait for that.
                return

            event = monitor.read()
            assert event.ch_type == iio.IIOChanType.IIO_PROXIMITY
            assert event.type == iio.IIOEventType.IIO_EV_TYPE_THRESH
            assert event.dir == iio.IIOEventDirection.IIO_EV_DIR_EITHER


@flaky_bus
def test_buffer(hw: I2CHardware[IRSD200], dev: IIODevice) -> None:
    trigger = read_str(Path("/sys/bus/iio/devices/trigger0/name"))
    write_int(dev.path / "buffer0/in_proximity_en", 1)
    write_str(dev.path / "trigger/current_trigger", trigger)
    with iio.IIOBuffer("/dev/iio:device0", bufidx=0) as buf:
        write_int(dev.path / "buffer0/length", 128)
        with sysfs_enable(dev.path / "buffer0/enable"):
            data = [
                (0x00, 0x00, 0x0000),
                (0x00, 0x01, 0x0001),
                (0x10, 0x00, 0x1000),
                (0x12, 0x34, 0x1234),
                (0xFF, 0xFF, 0xFFFF),
            ]
            for high, low, expected in data:
                hw.model.reg_write(REG_DATA_LO, low)
                hw.model.reg_write(REG_DATA_HI, high)
                hw.model.gen_irq(1 << 0)
                hw.kick()

                if hw.fault_injecting:
                    # When fault injecting, the buffer.read() could hang, so we
                    # can't wait for that.
                    continue

                assert buf.read("H")[0] == expected
