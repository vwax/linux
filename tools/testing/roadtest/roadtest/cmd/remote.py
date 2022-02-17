# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import importlib
import json
import os
from pathlib import Path
from typing import cast
from unittest import TestSuite, TextTestRunner

from roadtest import ENV_WORK_DIR
from roadtest.core import proxy


def main() -> None:
    workdir = Path(os.environ[ENV_WORK_DIR])
    with open(workdir / "tests.json") as f:
        testinfos = json.load(f)

    suite = TestSuite()
    for info in testinfos:
        id = info["id"]
        *modparts, clsname, method = id.split(".")

        fullname = ".".join(modparts)
        mod = importlib.import_module(fullname)

        cls = getattr(mod, clsname)
        test = cls(methodName=method)

        values = info["values"]
        if values:
            test.dts.values = values

        suite.addTest(test)

    runner = TextTestRunner(
        verbosity=0, buffer=False, resultclass=proxy.ProxyTextTestResult
    )
    result = cast(proxy.ProxyTextTestResult, runner.run(suite))

    proxyresult = result.to_proxy()
    with open(workdir / "results.json", "w") as f:
        json.dump(proxyresult, f)


if __name__ == "__main__":
    main()
