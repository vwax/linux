# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import abc
import importlib
import logging
import typing
from typing import Any, Literal, Optional

if typing.TYPE_CHECKING:
    # Avoid circular imports
    from .backend import Backend

logger = logging.getLogger(__name__)


class I2CBackend:
    def __init__(self, backend: "Backend") -> None:
        self.model: Optional[I2CModel] = None
        self.backend = backend

    def load_model(self, modname: str, clsname: str, *args: Any, **kwargs: Any) -> None:
        mod = importlib.import_module(modname)
        cls = getattr(mod, clsname)
        self.model = cls(*args, **kwargs, backend=self.backend)

    def unload_model(self) -> None:
        self.model = None

    def read(self, length: int) -> bytes:
        if not self.model:
            raise Exception("No I2C model loaded")

        return self.model.read(length)

    def write(self, data: bytes) -> None:
        if not self.model:
            raise Exception("No I2C model loaded")

        self.model.write(data)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.model, name)


class I2CModel(abc.ABC):
    def __init__(self, backend: "Backend") -> None:
        self.backend = backend

    @abc.abstractmethod
    def read(self, length: int) -> bytes:
        return bytes(length)

    @abc.abstractmethod
    def write(self, data: bytes) -> None:
        pass


class SMBusModel(I2CModel):
    def __init__(
        self,
        regbytes: int,
        byteorder: Literal["little", "big"] = "little",
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.reg_addr = 0x0
        self.regbytes = regbytes
        self.byteorder = byteorder

    @abc.abstractmethod
    def reg_read(self, addr: int) -> int:
        return 0

    @abc.abstractmethod
    def reg_write(self, addr: int, val: int) -> None:
        pass

    def val_to_bytes(self, val: int) -> bytes:
        return val.to_bytes(self.regbytes, self.byteorder)

    def bytes_to_val(self, data: bytes) -> int:
        return int.from_bytes(data, self.byteorder)

    def read(self, length: int) -> bytes:
        data = bytearray()
        for idx in range(0, length, self.regbytes):
            addr = self.reg_addr + idx
            val = self.reg_read(addr)
            logger.debug(f"SMBus read {addr=:#02x} {val=:#02x}")
            data += self.val_to_bytes(val)
        return bytes(data)

    def write(self, data: bytes) -> None:
        self.reg_addr = data[0]

        if len(data) > 1:
            length = len(data) - 1
            data = data[1:]
            assert length % self.regbytes == 0
            for idx in range(0, length, self.regbytes):
                val = self.bytes_to_val(data[idx : (idx + self.regbytes)])
                addr = self.reg_addr + idx
                self.backend.mock.reg_write(addr, val)
                self.reg_write(addr, val)
                logger.debug(f"SMBus write {addr=:#02x} {val=:#02x}")
        elif len(data) == 1:
            pass


class SimpleSMBusModel(SMBusModel):
    def __init__(self, regs: dict[int, int], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.regs = regs

    def reg_read(self, addr: int) -> int:
        val = self.regs[addr]
        return val

    def reg_write(self, addr: int, val: int) -> None:
        assert addr in self.regs
        self.regs[addr] = val
