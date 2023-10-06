# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import os
import subprocess
from pathlib import Path
from typing import Any, Iterator

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


def load_modules(files: Iterator[Path]) -> None:
    aliases = [
        f.read_text().rstrip() for f in files if not (f.parent / "driver").exists()
    ]
    if not aliases:
        return

    # "simple-battery" in compatible property is a special case as it's not a
    # real driver to be load, only checked in drivers/power/supply/power_supply_core.c
    # as a string value.

    simple_battery = "of:NbatteryT(null)Csimple-battery"
    if simple_battery in aliases:
        aliases.remove(simple_battery)

    moddir = Path(os.environ[ENV_BUILD_DIR]) / "modules"
    args = ["/sbin/modprobe", f"--dirname={moddir}", "-a"] + aliases
    subprocess.check_call(args)


def unload_modules() -> None:
    modules = [
        line.split(" ", maxsplit=1)[0]
        for line in Path("/proc/modules").read_text().splitlines()
    ]
    if not modules:
        return

    moddir = Path(os.environ[ENV_BUILD_DIR]) / "modules"
    args = ["/sbin/modprobe", f"--dirname={moddir}", "--remove", "--all"] + modules
    subprocess.check_call(args)


class Module:
    def __init__(self, name: str) -> None:
        self.name = name

    def __enter__(self) -> "Module":
        modprobe(self.name)
        return self

    def __exit__(self, *_: Any) -> None:
        rmmod(self.name)
