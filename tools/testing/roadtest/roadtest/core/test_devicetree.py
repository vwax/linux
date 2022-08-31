# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from pathlib import Path

from roadtest.core import devicetree
from roadtest.core.devicetree import SERIAL_BRIDGE, DtFragment, FragmentManager


def test_compile(tmp_path: Path) -> None:
    # We don't have the ksrcdir so we can't test if includes work.
    devicetree.compile(
        src="""
&i2c {
foo = <1>;
};
        """,
        dtb="test.dtb",
        workdir=tmp_path,
        ksrcdir=tmp_path,
    )
    assert (tmp_path / "test.dtb").exists()


def test_resources() -> None:
    fragman = FragmentManager()
    dt = DtFragment(
        """
i2ca=$i2ca$
gpio=$gpio$
spi=$spi$
name=$name$
nameb=$nameb$
seriala=$seriala$
serialb=$serialb$
i2cb=$i2cb$
""",
        i2c={
            "i2ca": devicetree.I2CAddr(),
            "i2cb": devicetree.I2CAddr(),
        },
        gpio={"gpio": devicetree.GpioPin()},
        spi={"spi": devicetree.SpiCS()},
        name={
            "name": devicetree.NodeName(),
            "nameb": devicetree.NodeName(prefix="b"),
        },
        serial={
            "seriala": devicetree.SerialAddr(),
            "serialb": devicetree.SerialAddr(),
        },
    )
    fragman.assign(dt)
    assert fragman.fragments == [
        SERIAL_BRIDGE.replace("$SERIALVAR$", "serial0").replace("$I2CVAR$", "0b")
        + SERIAL_BRIDGE.replace("$SERIALVAR$", "serial1").replace("$I2CVAR$", "0c")
        + """
i2ca=09
gpio=2
spi=00
name=node1
nameb=b2
seriala=serial0
serialb=serial1
i2cb=0a
"""
    ]
    assert dt.i2c["i2ca"].val == 9
    assert dt.i2c["i2cb"].val == 0xA
    assert dt.gpio["gpio"].val == 2
    assert dt.spi["spi"].val == 0
    assert dt.name["name"].val == 1
    assert dt.serial["seriala"].val == 0
    assert dt.serial["serialb"].val == 1
    assert dt.serial["seriala"].bridge_addr == 0x0B
    assert dt.serial["serialb"].bridge_addr == 0x0C
    assert dt.i2c["seriala-bridge"].val == 0x0B
    assert dt.i2c["serialb-bridge"].val == 0x0C
