# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import os
import subprocess
from pathlib import Path
from typing import Any

from roadtest import ENV_BUILD_DIR


def modprobe(modname: str, remove: bool = False) -> None:
    moddir = Path(os.environ[ENV_BUILD_DIR]) / "modules"
    args = []
    if remove:
        args.append("--remove")
    args += [f"--dirname={moddir}", modname]
    subprocess.check_output(["/sbin/modprobe"] + args)


def insmod(modname: str) -> None:
    modprobe(modname)


def rmmod(modname: str) -> None:
    subprocess.check_output(["/sbin/rmmod", modname])


class Module:
    def __init__(self, name: str) -> None:
        self.name = name

    def __enter__(self) -> "Module":
        modprobe(self.name)
        return self

    def __exit__(self, *_: Any) -> None:
        rmmod(self.name)
