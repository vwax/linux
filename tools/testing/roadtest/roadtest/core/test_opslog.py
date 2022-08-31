# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from pathlib import Path

from roadtest.core.opslog import OpsLogReader, OpsLogWriter


def test_opslog(tmp_path: Path) -> None:
    writer = OpsLogWriter(tmp_path)
    reader = OpsLogReader(tmp_path)

    assert reader.read_next() == []

    writer.write("1")
    writer.write("2")

    assert reader.read_next() == ["1", "2"]
    assert reader.read_next() == []

    writer.write("3")
    assert reader.read_next() == ["3"]
