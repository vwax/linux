# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from pathlib import Path

from roadtest.core.control import ControlProxy, ControlReader, ControlWriter


def test_control(tmp_path: Path) -> None:
    reader = ControlReader(tmp_path)
    writer = ControlWriter(tmp_path)

    values = []

    def append(new: int) -> None:
        nonlocal values
        values.append(new)

    vars = {"append": append}

    def call(method: str, arg: int) -> None:
        writer.write_cmd(f"{method}({arg})")

    proxy = ControlProxy(call=call)
    proxy.append(1)

    reader.process(vars)
    assert values == [1]

    proxy.append(2)
    writer.write_log("append(4)")
    proxy.append(3)

    reader.process(vars)
    assert values == [1, 2, 3]
    writer.close()
    assert writer.file.closed
