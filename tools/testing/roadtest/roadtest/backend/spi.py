# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import abc
import logging
import struct
from typing import Any, Literal, Sequence

from roadtest.backend.i2c import NonFlakyI2CModel

logger = logging.getLogger(__name__)


# Emulates an SC18IS602
class SPIModel(NonFlakyI2CModel):
    def __init__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.buffer = bytes()

    @abc.abstractmethod
    def xfer(self, indata: bytes) -> bytes:
        return indata

    def xfer_flaky(self, indata: bytes) -> bytes:
        self.update(indata)
        self.fault_inject()
        self.backend.mock.xfer(indata)
        outdata = self.xfer(indata)
        self.update(outdata)
        return outdata

    def read(self, length: int) -> bytes:
        data = self.buffer[:length]
        return data + bytes(length - len(data))

    def write(self, data: bytes) -> None:
        if len(data) == 0:
            return

        assert len(data) >= 2

        function = data[0]
        if function == 0xF0:
            # Configure, ignored for now
            return

        assert 0x01 <= function <= 0x0F
        self.buffer = self.xfer_flaky(data[1:])


class WordSPIModel(SPIModel):
    def __init__(
        self,
        wordbytes: Literal[1, 2, 4],
        byteorder: Literal["little", "big"] = "little",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        if byteorder == "little":
            self.bochar = "<"
        else:
            self.bochar = ">"

        self.wordbytes = wordbytes
        if wordbytes == 4:
            self.fmtchar = "L"
        elif wordbytes == 2:
            self.fmtchar = "H"
        else:
            self.fmtchar = "B"

        super().__init__(*args, **kwargs)

    @abc.abstractmethod
    def word_xfer(self, indata: Sequence[int]) -> Sequence[int]:
        return indata

    def xfer(self, indata: bytes) -> bytes:
        numwords = len(indata) // self.wordbytes
        fmt = f"{self.bochar}{numwords}{self.fmtchar}"

        inwords = struct.unpack(fmt, indata)
        outwords = self.word_xfer(inwords)

        return struct.pack(fmt, *outwords)
