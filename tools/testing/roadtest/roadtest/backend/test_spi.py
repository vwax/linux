# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from typing import Any, Sequence
from unittest.mock import MagicMock

from roadtest.backend.spi import WordSPIModel


class DummyModel(WordSPIModel):
    def __init__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.mock = MagicMock()

    def word_xfer(self, indata: Sequence[int]) -> Sequence[int]:
        self.mock(indata)
        return super().word_xfer(indata)


def test_word_xfer() -> None:
    table: list[tuple[int, str, bytes, int]] = [
        (1, "big", bytes([0x12]), 0x12),
        (1, "little", bytes([0x12]), 0x12),
        (2, "big", bytes([0x12, 0x34]), 0x1234),
        (2, "little", bytes([0x34, 0x12]), 0x1234),
        (4, "big", bytes([0x12, 0x34, 0x56, 0x78]), 0x12345678),
        (4, "little", bytes([0x78, 0x56, 0x34, 0x12]), 0x12345678),
    ]

    for wordbytes, byteorder, data, word in table:
        m = DummyModel(wordbytes=wordbytes, byteorder=byteorder, backend=MagicMock())
        assert data == m.xfer(data)
        m.mock.assert_called_once_with((word,))
