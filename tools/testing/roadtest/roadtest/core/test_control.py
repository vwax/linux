# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from pathlib import Path
from typing import Any, cast

from roadtest.core.control import ControlProxy, ControlReader, ControlWriter


class SubHandler:
    def __init__(self) -> None:
        self.values: list[int] = []

    def append(self, val1: int, val2: int, val3: int = 99) -> None:
        self.values.append(val1)
        self.values.append(val2)
        self.values.append(val3)


class Handler:
    def __init__(self) -> None:
        self.values: list[int] = []
        self.subhandler = SubHandler()

    def append(self, val: int) -> None:
        self.values.append(val)


def test_control(tmp_path: Path) -> None:
    reader = ControlReader(tmp_path)
    writer = ControlWriter(tmp_path)

    handler = Handler()
    vars = {"handler": handler}

    def call(method: str, *args: Any, **kwargs: Any) -> None:
        writer.write_cmd(f"{method}(*{str(args)}, **{str(kwargs)})")

    proxy = cast(Handler, ControlProxy(name="handler", call=call))
    proxy.append(1)

    reader.process(vars)
    assert handler.values == [1]

    proxy.append(2)
    writer.write_log("append(4)")
    proxy.append(3)

    reader.process(vars)
    assert handler.values == [1, 2, 3]

    proxy.values[0] = 111
    reader.process(vars)
    assert handler.values == [111, 2, 3]

    proxy.values = [99, 100]
    reader.process(vars)
    assert handler.values == [99, 100]
    # Only one-way communication
    assert proxy.values != [99, 100]

    proxy.values[1] = 101
    reader.process(vars)
    assert handler.values == [99, 101]

    proxy.subhandler.append(500, 600, val3=700)
    reader.process(vars)
    assert handler.subhandler.values == [500, 600, 700]

    writer.close()
    assert writer.file.closed


def test_parital(tmp_path: Path) -> None:
    reader = ControlReader(tmp_path)
    writer = ControlWriter(tmp_path)

    values = []

    def append(new: int) -> None:
        nonlocal values
        values.append(new)

    vars = {"append": append}

    writer.file.write("append(1)\n")

    writer.file.write("append(")
    writer.file.flush()
    reader.process(vars)

    writer.file.write("2")
    writer.file.flush()
    reader.process(vars)

    writer.file.write(")\nappend(3)")
    writer.file.flush()
    reader.process(vars)

    writer.file.write("\n")
    writer.file.flush()
    reader.process(vars)

    writer.file.write("append(4)\n")
    reader.process(vars)

    assert values == [1, 2, 3, 4]
