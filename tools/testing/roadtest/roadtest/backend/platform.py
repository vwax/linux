# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import abc
import importlib
import logging
import typing
from typing import Any, Optional

if typing.TYPE_CHECKING:
    # Avoid circular imports
    from .backend import Backend

logger = logging.getLogger(__name__)


class PlatformBackend:
    def __init__(self, backend: "Backend") -> None:
        self.model: Optional[PlatformModel] = None
        self.backend = backend

    def load_model(self, modname: str, clsname: str, *args: Any, **kwargs: Any) -> None:
        mod = importlib.import_module(modname)
        cls = getattr(mod, clsname)
        self.model = cls(*args, **kwargs, backend=self.backend)

    def unload_model(self) -> None:
        self.model = None

    def read(self, addr: int, size: int) -> int:
        if not self.model:
            raise Exception("No platform model loaded")

        return self.model.read(addr, size)

    def write(self, addr: int, size: int, value: int) -> None:
        if not self.model:
            raise Exception("No platform model loaded")

        self.model.write(addr, size, value)


class PlatformModel(abc.ABC):
    def __init__(self, backend: "Backend") -> None:
        self.backend = backend

    @abc.abstractmethod
    def read(self, addr: int, size: int) -> int:
        return 0

    @abc.abstractmethod
    def write(self, addr: int, size: int, value: int) -> None:
        pass


class Reg32PlatformModel(PlatformModel):
    @abc.abstractmethod
    def readl(self, addr: int) -> int:
        return 0

    def read(self, addr: int, size: int) -> int:
        assert size == 4
        addr &= 0xFFFF
        self.backend.mock.reg_read(addr)
        return self.readl(addr)

    @abc.abstractmethod
    def writel(self, addr: int, value: int) -> None:
        pass

    def write(self, addr: int, size: int, value: int) -> None:
        assert size == 4
        addr &= 0xFFFF
        self.backend.mock.reg_write(addr, value)
        self.writel(addr, value)
