# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import json
import os
import shlex
import signal
import subprocess
import textwrap
import unittest
from pathlib import Path
from typing import Any, ClassVar, Optional, Tuple, cast
from unittest import TestResult

from roadtest import ENV_BUILD_DIR, ENV_WORK_DIR

from . import devicetree
from .log import LogParser


class UMLTestCase(unittest.TestCase):
    run_separately: ClassVar[bool] = False
    dts: ClassVar[Optional[devicetree.DtFragment]] = None


class UMLSuite(unittest.TestSuite):
    def __init__(
        self,
        timeout: int,
        workdir: str,
        builddir: str,
        ksrcdir: str,
        uml_args_pre: list[str],
        uml_args_post: list[str],
        shell: bool,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.timeout = timeout
        self.workdir = Path(workdir).resolve()
        self.builddir = Path(builddir)
        self.ksrcdir = Path(ksrcdir)
        self.uml_args_pre = uml_args_pre
        self.uml_args_post = uml_args_post
        self.shell = shell

        self.backendlog = self.workdir / "backend.txt"
        self.umllog = self.workdir / "uml.txt"

        # Used from the roadtest.cmd.remote running inside UML
        self.testfile = self.workdir / "tests.json"
        self.resultfile = self.workdir / "results.json"

    def run(
        self, result: unittest.TestResult, debug: bool = False
    ) -> unittest.TestResult:
        pwd = os.getcwd()

        os.makedirs(self.workdir, exist_ok=True)
        workdir = self.workdir

        tests = cast(list[UMLTestCase], list(self))

        os.environ[ENV_WORK_DIR] = str(workdir)
        os.environ[ENV_BUILD_DIR] = str(self.builddir)

        dt = devicetree.Devicetree(workdir=workdir, ksrcdir=self.ksrcdir)
        dt.assemble([test.dts for test in tests if test.dts])
        dt.compile("test.dtb")

        testinfos = []
        ids = []
        for t in tests:
            id = t.id()
            # This fixup is needed when discover is done starting from "roadtest"
            if not id.startswith("roadtest."):
                id = f"roadtest.{id}"
            ids.append(id)

            testinfos.append({"id": id, "values": t.dts.values if t.dts else {}})

        with self.testfile.open("w") as f:
            json.dump(testinfos, f)

        uml_args = [
            str(self.builddir / "vmlinux"),
            f"PYTHONPATH={pwd}",
            f"{ENV_WORK_DIR}={workdir}",
            f"{ENV_BUILD_DIR}={self.builddir}",
            # Should be enough for anybody?
            "mem=64M",
            "dtb=test.dtb",
            "rootfstype=hostfs",
            "rw",
            f"init={pwd}/init.sh",
            f"uml_dir={workdir}",
            "umid=uml",
            # ProxyTextTestResult writes to /dev/kmsg
            "printk.devkmsg=on",
            "slub_debug",
            # For ease of debugging
            "no_hash_pointers",
        ]

        if self.shell:
            # See init.sh
            uml_args += ["ROADTEST_SHELL=1"]
        else:
            # Set by slub_debug
            TAINT_BAD_PAGE = 1 << 5
            uml_args += [
                # init.sh increases the loglevel after bootup.
                "quiet",
                "panic_on_warn=1",
                f"panic_on_taint={TAINT_BAD_PAGE}",
                "oops=panic",
                # Speeds up delays, but as a consequence also causes
                # 100% CPU consumption at an idle shell prompt.
                "time-travel",
            ]

        main_script = (Path(__file__).parent / "../backend/main.py").resolve()

        args = (
            [
                str(self.builddir / "roadtest-backend"),
                # The socket locations are also present in the devicetree.
                f"--gpio-socket={workdir}/gpio.sock",
                f"--i2c-socket={workdir}/i2c.sock",
                f"--main-script={main_script}",
                "--",
            ]
            + self.uml_args_pre
            + uml_args
            + self.uml_args_post
        )

        print(
            "Running backend/UML with: {}".format(
                " ".join([shlex.quote(a) for a in args])
            )
        )

        # Truncate instead of deleting so that tail -f can be used to monitor
        # the log across runs.
        self.backendlog.write_text("")
        self.umllog.write_text("")
        self.resultfile.unlink(missing_ok=True)

        umlpidfile = workdir / "uml/pid"
        umlpidfile.unlink(missing_ok=True)

        newenv = dict(os.environ, PYTHONPATH=pwd)

        try:
            process = None
            with self.backendlog.open("w") as f:
                process = subprocess.Popen(
                    args,
                    env=newenv,
                    stdin=subprocess.PIPE,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    preexec_fn=os.setsid,
                )
                process.wait(self.timeout if self.timeout else None)
        except subprocess.TimeoutExpired:
            pass
        finally:
            try:
                if process:
                    os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                pid = int(umlpidfile.read_text())
                os.killpg(pid, signal.SIGKILL)
            except (FileNotFoundError, ProcessLookupError):
                pass

        if process and process.returncode is not None and process.returncode != 0:
            with self.backendlog.open("a") as f:
                f.write(f"<Backend exited with error code {process.returncode}>\n")

        try:
            with self.resultfile.open("r") as f:
                proxy = json.load(f)
        except FileNotFoundError:
            # UML crashed, timed out, etc
            proxy = None

        return self._convert_results(proxy, tests, result)

    def _parse_status(self, id: str, proxy: dict) -> Tuple[str, str]:
        if not proxy:
            return "ERROR", "No result.  UML or backend crashed?\n"

        try:
            _, tb = next(e for e in proxy["successes"] if e[0] == id)
            return "ok", ""
        except StopIteration:
            pass

        try:
            _, tb = next(e for e in proxy["errors"] if e[0] == id)
            return "ERROR", tb
        except StopIteration:
            pass

        try:
            _, tb = next(e for e in proxy["failures"] if e[0] == id)
            return "FAIL", tb
        except StopIteration:
            pass

        # setupClass, etc
        if proxy["errors"]:
            _, tb = proxy["errors"][0]
            return "ERROR", tb

        raise Exception("Unable to parse status")

    def _get_log(
        self, name: str, parser: LogParser, id: str, full_if_none: bool
    ) -> Optional[str]:
        testloglines = parser.get_testcase_log(id)
        tb = None
        if testloglines:
            tb = "\n".join([f"{name} log:"] + [" " + line for line in testloglines])
        elif full_if_none and not parser.has_any():
            if parser.raw:
                tb = "\n".join(
                    [f"Full {name} log:", textwrap.indent(parser.raw, " ").rstrip()]
                )
            else:
                tb = f"\nNo {name} log found."

        return tb

    def _convert_results(
        self,
        proxy: dict,
        tests: list[UMLTestCase],
        result: TestResult,
    ) -> TestResult:
        umllog = LogParser(self.umllog)
        backendlog = LogParser(self.backendlog)

        first_fail = True
        for test in tests:
            assert isinstance(test, unittest.TestCase)

            id = test.id()
            if not id.startswith("roadtest."):
                id = f"roadtest.{id}"

            status, tb = self._parse_status(id, proxy)
            if status != "ok":
                parts = []

                backendtb = self._get_log("Backend", backendlog, id, first_fail)
                if backendtb:
                    parts.append(backendtb)

                umltb = self._get_log("UML", umllog, id, first_fail)
                if umltb:
                    parts.append(umltb)

                # In the case of no START/STOP markers at all in the logs, we include
                # the full logs, but only do it in the first failing test case to
                # reduce noise.
                first_fail = False
                tb = "\n\n".join(parts + [tb])

            if status == "ERROR":
                result.errors.append((test, tb))
            elif status == "FAIL":
                result.failures.append((test, tb))

            print(f"{test} ... {status}")
            result.testsRun += 1

        return result
