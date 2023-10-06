# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import abc
import hashlib
import importlib
import logging
import typing
from collections import deque
from typing import Any, Literal, Optional

if typing.TYPE_CHECKING:
    # Avoid circular imports
    from .backend import Backend

logger = logging.getLogger(__name__)
faultlogger = logging.getLogger("fault")
faultlogger.setLevel(logging.INFO)


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

    def read(self, addr: int, length: int) -> bytes:
        if not self.model:
            raise Exception("No I2C model loaded")

        return self.model.read_flaky_addr(addr >> 1, length)

    def write(self, addr: int, data: bytes) -> None:
        if not self.model:
            raise Exception("No I2C model loaded")

        self.model.write_flaky_addr(addr >> 1, data)


class I2CModel(abc.ABC):
    def __init__(self, backend: "Backend") -> None:
        self.backend = backend
        self.failed: set[str] = set()
        self.should_fail_next = 0
        self.hash = hashlib.md5()
        self.last_reads: deque[tuple] = deque(maxlen=2)
        self.last_writes: deque[tuple] = deque(maxlen=2)

    def fail_next(self, counter: int) -> None:
        faultlogger.debug(f"fail_next {counter=}")
        self.should_fail_next = counter
        self.hash = hashlib.md5()

    def fault_inject(self) -> None:
        if self.should_fail_next <= 0:
            return

        self.should_fail_next -= 1
        if self.should_fail_next == 0:
            digest = self.hash.hexdigest()
            faultlogger.debug(f"should fail {digest=}")
            if digest in self.failed:
                faultlogger.debug(f"skip fail for {digest=}")
                self.should_fail_next = 1
                return

            # if len(set(self.last_reads)) == 1 and len(set(self.last_writes)) == 1:
            #     logging.debug(
            #         f"skip fail for repeated transactions reads: {self.last_reads} writes: {self.last_writes}"
            #     )
            #     self.should_fail_next = 1
            #     return

            self.backend.mock.fault_injected(1)
            self.failed.add(digest)
            raise Exception("fault injection")

    def update(self, data: bytes) -> None:
        faultlogger.debug(f"update fault with {data!r}")
        self.hash.update(data)

    def record_read(self, data: bytes) -> None:
        faultlogger.debug(f"update read with {data!r}")
        self.last_reads.append(tuple(data))

    def record_write(self, data: bytes) -> None:
        faultlogger.debug(f"update write with {data!r}")
        self.last_writes.append(tuple(data))

    def reset(self) -> None:
        self.failed = set()

    def write_flaky_addr(self, addr: int, data: bytes) -> None:
        self.write_flaky(data)

    def read_flaky_addr(self, addr: int, length: int) -> bytes:
        return self.read_flaky(length)

    def read_flaky(self, length: int) -> bytes:
        self.fault_inject()
        out = self.read(length)
        self.update(out)
        return out

    def write_flaky(self, data: bytes) -> None:
        self.fault_inject()
        self.write(data)
        self.update(data)

    @abc.abstractmethod
    def read(self, length: int) -> bytes:
        return bytes(length)

    @abc.abstractmethod
    def write(self, data: bytes) -> None:
        pass


# For sub-models which implement flakiness themselves and
# thus want to avoid unnecessary flakiness at the I2C level
class NonFlakyI2CModel(I2CModel):
    def read_flaky(self, length: int) -> bytes:
        return self.read(length)

    def write_flaky(self, data: bytes) -> None:
        self.write(data)


class SMBusModel(NonFlakyI2CModel):
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
        # pyright seems to need the explicit type
        self.byteorder: Literal["little", "big"] = byteorder

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
        self.fault_inject()

        data = bytearray()
        for idx in range(0, length, self.regbytes):
            addr = self.reg_addr + idx
            val = self.reg_read(addr)
            logger.debug(f"SMBus read {addr=:#02x} {val=:#02x}")
            data += self.val_to_bytes(val)

        out = bytes(data)
        self.update(out)
        self.record_read(data)
        return out

    def write(self, data: bytes) -> None:
        self.reg_addr = data[0]
        self.update(data)
        self.record_write(data)

        if len(data) > 1:
            self.fault_inject()

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
