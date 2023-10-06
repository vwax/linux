# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

from roadtest import ENV_WORK_DIR

CONTROL_FILE = "control.txt"

logger = logging.getLogger(__name__)


class ControlProxy:
    def __init__(self, call: Callable, name: Optional[str] = None):
        self.__name = name
        self.__prefix = f"{name}." if name is not None else ""
        self.__call = call

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.__call(self.__name, *args, **kwargs)

    def __getattr__(self, name: str) -> Callable:
        attr = ControlProxy(name=f"{self.__prefix}{name}", call=self.__call)
        super().__setattr__(name, attr)
        return attr

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith(f"_{self.__class__.__name__}"):
            super().__setattr__(name, value)
            return

        self.__call(f"{self.__prefix}__setattr__", name, value)

        # We don't call __setattr__ here on purpose.  This proxy provides
        # only one-way communication to the model so we don't want the tests
        # to think they're able to read data from it via this interface.

    def __setitem__(self, name: str, value: Any) -> None:
        self.__call(f"{self.__prefix}__setitem__", name, value)

    def __getitem__(self, name: str) -> Any:
        return ControlProxy(
            name=f"{self.__prefix}__getitem__({name})", call=self.__call
        )


class ControlReader:
    def __init__(
        self, work_dir: Optional[Path] = None, filename: str = CONTROL_FILE
    ) -> None:
        if not work_dir:
            work_dir = Path(os.environ[ENV_WORK_DIR])

        path = work_dir / filename
        path.unlink(missing_ok=True)
        path.write_text("")

        self.partial = ""
        self.file = path.open("r")

    def process(self, vars: dict) -> None:
        for line in self.file.readlines():
            if not line.endswith("\n"):
                self.partial += line
                continue

            cmd = line.rstrip()
            if self.partial:
                cmd = self.partial + cmd
                self.partial = ""

            if cmd.startswith("# "):
                logger.info(line[2:].rstrip())
                continue

            logger.debug(cmd)
            eval(cmd, vars)


class ControlWriter:
    def __init__(
        self, work_dir: Optional[Path] = None, filename: str = CONTROL_FILE
    ) -> None:
        if not work_dir:
            work_dir = Path(os.environ[ENV_WORK_DIR])
        self.file = (work_dir / filename).open("a", buffering=1)

    def write_cmd(self, line: str) -> None:
        self.file.write(line + "\n")

    def write_log(self, line: str) -> None:
        self.file.write(f"# {line}\n")

    def close(self) -> None:
        self.file.close()
