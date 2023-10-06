# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import importlib
import json
import os
from pathlib import Path

import pytest

from roadtest import ENV_WORK_DIR
from roadtest.support.modules import load_modules


class MyPlugin:
    def __init__(self, testinfos: dict) -> None:
        self.testinfos = testinfos

    def pytest_configure(self, config: pytest.Config) -> None:
        config.option.verbose = 1

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        for info in self.testinfos:
            id = info["id"]
            res = info["resources"]
            if not res:
                continue

            modparts = id.split("::")[0].removesuffix(".py")
            package = ".".join(modparts.split("/"))
            mod = importlib.import_module(package)

            mod.dts.load_resources(info["resources"])


def main() -> None:
    load_modules(Path("/sys/devices/").rglob("modalias"))

    pytest.register_assert_rewrite("roadtest.core")

    workdir = Path(os.environ[ENV_WORK_DIR])
    with open(workdir / "tests.json") as f:
        info = json.load(f)

    testinfos = info["tests"]

    tests = [t["id"] for t in testinfos]
    pytest.main(
        [
            "-proadtest.pytest.target",
            "-pno:terminal",
            # Allows prints to be seen both in the backend log and from the
            # pytest runner (displayed with -rP for passing tests).
            "--capture=tee-sys",
            # Do not read configuration from pyproject.toml, since that's
            # set up for the host system.
            "-c/dev/null",
            # Using the /dev/null as the config sets the root directory to /dev,
            # which leads to some wierdness with the test names, so reset it.
            "--rootdir=.",
        ]
        + info["extra_cmdline_args"]
        + tests,
        plugins=[MyPlugin(testinfos)],
    )


if __name__ == "__main__":
    main()
