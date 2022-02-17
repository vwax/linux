# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import logging
import os
from pathlib import Path
from typing import Optional

from roadtest import ENV_WORK_DIR

CONTROL_FILE = "control.txt"

logger = logging.getLogger(__name__)


class ControlReader:
    def __init__(self, work_dir: Optional[Path] = None) -> None:
        if not work_dir:
            work_dir = Path(os.environ[ENV_WORK_DIR])

        path = work_dir / CONTROL_FILE
        path.unlink(missing_ok=True)
        path.write_text("")

        self.file = path.open("r")

    def process(self, vars: dict) -> None:
        for line in self.file.readlines():
            cmd = line.rstrip()

            if cmd.startswith("# "):
                logger.info(line[2:].rstrip())
                continue

            logger.debug(cmd)
            eval(cmd, vars)


class ControlWriter:
    def __init__(self, work_dir: Optional[Path] = None) -> None:
        if not work_dir:
            work_dir = Path(os.environ[ENV_WORK_DIR])
        self.file = (work_dir / CONTROL_FILE).open("a", buffering=1)

    def write_cmd(self, line: str) -> None:
        self.file.write(line + "\n")

    def write_log(self, line: str) -> None:
        self.file.write(f"# {line}\n")

    def close(self) -> None:
        self.file.close()
