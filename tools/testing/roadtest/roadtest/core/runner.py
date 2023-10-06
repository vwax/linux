# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB


import argparse
import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

T = TypeVar("T", bound="RunnerArgs")


@dataclass
class RunnerArgs:
    work_dir: Path
    build_dir: Path
    ksrc_dir: Path
    tests_per_job: int
    parallel: int
    bootargs: list[str]
    timeout: int
    shell: bool
    gdb: bool

    @classmethod
    def from_namespace(cls: type[T], ns: argparse.Namespace) -> T:
        opts = vars(ns)
        return cls(**{f.name: opts[f"rt_{f.name}"] for f in dataclasses.fields(cls)})

    def __post_init__(self) -> None:
        if self.parallel <= 0:
            self.parallel = 1

        bootargs = [
            # The framework uses /dev/kmsg to print START/STOP logs.
            "printk.devkmsg=on",
            # Make debugging simpler.
            "no_hash_pointers",
            "virt-pci.max_delay_us=4000000",
        ]

        if self.shell:
            self.parallel = 1
            self.timeout = 0
            # See init.sh
            bootargs.append("ROADTEST_SHELL=1")

            assert any(
                p.startswith("con=") for p in self.bootargs
            ), "Error: --rt-shell used but no con= UML argument specified"
        else:
            # This is set by slub debug
            TAINT_BAD_PAGE = 1 << 5
            bootargs += [
                # The bootup logs are usually uninteresting.  init.sh increases
                # the loglevel after bootup.
                "quiet",
                "panic_on_warn=1",
                f"panic_on_taint={TAINT_BAD_PAGE}",
                "oops=panic",
            ]

        if self.gdb:
            self.parallel = 1
            self.timeout = 0

        self.bootargs = bootargs + self.bootargs
