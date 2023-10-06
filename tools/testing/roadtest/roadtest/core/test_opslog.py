# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from pathlib import Path

from roadtest.core.opslog import OpsLogReader, OpsLogWriter


def test_opslog(tmp_path: Path) -> None:
    writer = OpsLogWriter(tmp_path)
    reader = OpsLogReader(tmp_path)

    assert reader.read_next() == []

    writer.write("111")
    writer.write("222")

    assert reader.read_next() == ["111", "222"]
    assert reader.read_next() == []

    writer.write("333")
    assert reader.read_next() == ["333"]


def test_partial(tmp_path: Path) -> None:
    writer = OpsLogWriter(tmp_path)
    reader = OpsLogReader(tmp_path)

    assert reader.read_next() == []

    writer.write("111")
    writer.file.write("22")
    writer.file.flush()

    assert reader.read_next() == ["111"]

    writer.file.write("2")
    writer.file.flush()

    assert reader.read_next() == []

    writer.file.write("\n3")
    writer.file.flush()

    assert reader.read_next() == ["222"]

    writer.file.write("33\n")
    writer.file.flush()

    assert reader.read_next() == ["333"]
