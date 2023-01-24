# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import inspect
import os
import signal
import subprocess
import sys
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional, cast

from roadtest import ENV_BUILD_DIR, ENV_KSRC_DIR, ENV_WORK_DIR
from roadtest.backend.i2c import I2CModel
from roadtest.core.control import ControlReader
from roadtest.core.hardware import Hardware
from roadtest.core.runner import RunnerArgs


def flaky_bus(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        hw = cast(Hardware[I2CModel], kwargs.get("hw"))
        request = kwargs.pop("request")
        handle = True
        try:
            # Only fault inject on the first run of a parameterized test suite
            if c := request.node.callspec:
                handle = all(v == 0 for v in c.indices.values())
        except AttributeError:
            pass

        l = None
        # l = open("/dev/kmsg", "w", buffering=1)
        # l.write(f"flaky_bus {func} {handle=}\n")

        hw.fault_injecting = True

        if handle:
            stop = False
            for i in range(1, 10, 1):
                hw.model.fail_next(i)
                ex = None
                try:
                    if l:
                        l.write(f"running function {i=}!\n")
                    func(*args, **kwargs)
                except Exception as _ex:
                    ex = _ex
                finally:
                    hw.model.fail_next(0)
                    if not hw.update_mock().fault_injected.called:
                        if l:
                            l.write("fault NOT injected!\n")
                        stop = True
                        if ex is not None:
                            raise ex
                    else:
                        if l:
                            l.write("fault injected!\n")

                if stop:
                    break

        # Even though the last iteration of the loop above has succesfully run
        # the function, we still need to call it again since the test function
        # could have changed its behaviour based on hw.fault_injecting.
        hw.fault_injecting = False
        func(*args, **kwargs)

    sig = inspect.signature(wrapper)
    params = list(sig.parameters.values()) + [
        inspect.Parameter("request", inspect.Parameter.KEYWORD_ONLY)
    ]

    wrapper.__signature__ = sig.replace(parameters=params)  # type: ignore

    return wrapper


class UMLInstance:
    def __init__(
        self,
        id: int,
        workdir: Path,
        runner_args: RunnerArgs,
    ) -> None:
        self.id = id
        self.workdir = workdir
        self.builddir = runner_args.build_dir
        self.ksrcdir = runner_args.ksrc_dir
        self.umllog = self.workdir / "uml.txt"
        self.backendlog = self.workdir / "backend.txt"
        self.resultfile = self.workdir / "results.json"
        self.umlpidfile = self.workdir / "uml/pid"
        self.runner_args = runner_args

        self.proc: Optional[subprocess.Popen] = None

        self.resultstream = ControlReader(filename="resultstream.txt", work_dir=workdir)

        # Truncate instead of deleting so that tail -f can be used to monitor
        # the log across runs.
        self.backendlog.write_text("")
        self.umllog.write_text("")
        self.resultfile.unlink(missing_ok=True)
        self.umlpidfile.unlink(missing_ok=True)

    def __str__(self) -> str:
        return f"uml{self.id:02d}"

    def run(self) -> subprocess.Popen:
        pwd = os.getcwd()

        env = dict(os.environ)
        env[ENV_WORK_DIR] = str(self.workdir)
        env[ENV_BUILD_DIR] = str(self.builddir)
        ver = sys.version_info
        # Change TMPDIR to allow running inside containers which don't
        # have /dev/shm which UML wants.
        env["TMPDIR"] = str(self.workdir)
        env["PYTHONPATH"] = ":".join(
            [
                pwd,
                str(
                    self.runner_args.ksrc_dir
                    / f"venv/lib/python{ver.major}.{ver.minor}/site-packages/"
                ),
            ]
        )

        uml_args = [
            str(self.builddir / "vmlinux"),
            f"PYTHONPATH={pwd}",
            f"{ENV_WORK_DIR}={self.workdir}",
            f"{ENV_BUILD_DIR}={self.builddir}",
            f"{ENV_KSRC_DIR}={self.ksrcdir}",
            "mem=128M",
            "dtb=test.dtb",
            "rootfstype=hostfs",
            "rw",
            f"init={pwd}/init.sh",
            f"uml_dir={self.workdir}",
            "umid=uml",
        ]

        if not self.runner_args.shell:
            # Speeds up delays, but as a consequence also causes
            # 100% CPU consumption at an idle shell prompt.
            uml_args.append("time-travel")

        main_script = (Path(__file__).parent / "../backend/main.py").resolve()

        prepend = []
        if port := self.runner_args.gdb:
            prepend = ["gdbserver", f":{port}"]
            print(
                f"Connect with: gdb-multiarch -ex 'target remote :{port}' {self.builddir}/vmlinux"
            )

        args = (
            [
                str(self.builddir / "roadtest-backend"),
                # The socket locations are also present in the devicetree.
                f"--gpio-socket={self.workdir}/gpio.sock",
                f"--i2c-socket={self.workdir}/i2c.sock",
                f"--pci-socket={self.workdir}/pci.sock",
                f"--main-script={main_script}",
                "--",
            ]
            + prepend
            + uml_args
            + self.runner_args.bootargs
        )

        backendlogf = self.backendlog.open("w")
        try:
            proc = subprocess.Popen(
                args,
                env=env,
                stdin=subprocess.PIPE,
                stdout=backendlogf,
                stderr=subprocess.STDOUT,
                text=True,
                preexec_fn=os.setsid,
            )
        except:
            backendlogf.close()
            raise

        self.start_time = datetime.now()
        self.backendlogf = backendlogf
        self.proc = proc

        return proc

    def stop(self) -> None:
        proc = self.proc
        if proc is None:
            return

        try:
            if proc:
                os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

        try:
            pid = int(self.umlpidfile.read_text())
            os.killpg(pid, signal.SIGKILL)
        except (FileNotFoundError, ProcessLookupError):
            pass

        if proc and proc.returncode is not None and proc.returncode != 0:
            self.backendlogf.write(
                f"<Backend exited with error code {proc.returncode}>\n"
            )

        self.backendlogf.close()
