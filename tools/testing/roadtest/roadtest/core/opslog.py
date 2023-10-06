# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import os
from pathlib import Path

OPSLOG_FILE = "opslog.txt"


class OpsLogWriter:
    def __init__(self, work: Path) -> None:
        path = work / OPSLOG_FILE
        path.unlink(missing_ok=True)
        self.file = open(path, "a", buffering=1)

    def write(self, line: str) -> None:
        self.file.write(line + "\n")


class OpsLogReader:
    def __init__(self, work: Path) -> None:
        self.path = work / OPSLOG_FILE
        self.opslogpos = 0
        self.partial = ""

    def read_next(self) -> list[str]:
        # There is a problem in hostfs (see Hostfs Caveats) which means
        # that reads from UML on a file which is extended on the host don't see
        # the new data unless we open and close the file, so we can't open once
        # and use readlines().
        with open(self.path, "r") as f:
            os.lseek(f.fileno(), self.opslogpos, os.SEEK_SET)

            opslog = []
            for line in f.readlines():
                if not line.endswith("\n"):
                    self.partial += line
                    continue

                op = line.rstrip()
                if self.partial:
                    op = self.partial + op
                    self.partial = ""

                opslog.append(op)

            self.opslogpos = os.lseek(f.fileno(), 0, os.SEEK_CUR)

        return opslog
