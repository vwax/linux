# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import abc
import importlib
import logging
import typing
from typing import Any, Final, Optional

if typing.TYPE_CHECKING:
    # Avoid circular imports
    from .backend import Backend

logger = logging.getLogger(__name__)

BCMA_SCAN_ER_VALID: Final = 1
BCMA_SCAN_ER_TAG_END: Final = 0xE
BCMA_CORE_SIZE: Final = 0x1000


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
        if addr == 0:
            # See bcma_bus_scan() / bcma_get_next_core()
            return BCMA_SCAN_ER_TAG_END | BCMA_SCAN_ER_VALID
        elif addr < BCMA_CORE_SIZE:
            return 0

        if not self.model:
            raise Exception("No platform model loaded")

        return self.model.read(addr, size)

    def write(self, addr: int, size: int, value: int) -> None:
        if not self.model:
            raise Exception("No platform model loaded")

        self.model.write(addr, size, value)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.model, name)


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
        return self.readl(addr)

    @abc.abstractmethod
    def writel(self, addr: int, value: int) -> None:
        pass

    def write(self, addr: int, size: int, value: int) -> None:
        assert size == 4
        self.writel(addr, value)
