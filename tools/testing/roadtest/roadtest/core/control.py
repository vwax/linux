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
    def __init__(self, call: Callable):
        self.call = call

    def __getattr__(self, name: str) -> Callable:
        def func(*args: Any, **kwargs: Any) -> None:
            self.call(name, *args, **kwargs)

        setattr(self, name, func)
        return func


class ControlReader:
    def __init__(
        self, work_dir: Optional[Path] = None, filename: str = CONTROL_FILE
    ) -> None:
        if not work_dir:
            work_dir = Path(os.environ[ENV_WORK_DIR])

        path = work_dir / filename
        path.unlink(missing_ok=True)
        path.write_text("")

        self.file = path.open("r")

    def process(self, vars: dict) -> None:
        # XXX handle partial read
        for line in self.file.readlines():
            cmd = line.rstrip()

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
