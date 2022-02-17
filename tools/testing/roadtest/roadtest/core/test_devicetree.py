# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import tempfile
import unittest
from pathlib import Path

from . import devicetree


class TestDevicetree(unittest.TestCase):
    def test_compile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            # We don't have the ksrcdir so we can't test if includes work.
            dt = devicetree.Devicetree(tmpdir, tmpdir)

            dt.assemble(
                [
                    devicetree.DtFragment(
                        src="""
&i2c {
    foo = <1>;
};
            """
                    )
                ]
            )
            dt.compile("test.dtb")
            dtb = tmpdir / "test.dtb"
            self.assertTrue((dtb).exists())
