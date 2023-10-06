import inspect
import json
import os
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import pytest

from roadtest.core import devicetree
from roadtest.core.log import LogParser
from roadtest.core.runner import RunnerArgs
from roadtest.core.suite import UMLInstance


# These ids are shown for each test when run with -v.  The interface
# is undocumented but is used by pytest-xdist.
class Gateway:
    def __init__(self, id: str) -> None:
        self.id = id


class Worker:
    def __init__(self, id: str) -> None:
        self.gateway = Gateway(id)


# The default function expects to display some Python information the
# worker, but this is irrelevant for us, so we patch it out with this
# nop version.
def getworkerinfoline(node: Worker) -> str:
    return ""


class TargetCrashItem(pytest.Item):
    uml: UMLInstance

    def setup(self) -> None:
        log = LogParser(self.uml.umllog).get_last_log()
        if log:
            self.add_report_section(
                when="log",
                key=f"{self.uml} UML",
                content="\n".join(log),
            )
        log = LogParser(self.uml.backendlog).get_last_log()
        if log:
            self.add_report_section(
                when="log",
                key=f"{self.uml} Backend",
                content="\n".join(log),
            )
        pytest.fail(
            reason=f"Some tests not run, {self.uml} crashed/hanged.",
            pytrace=False,
        )


class WarningItem(pytest.Item):
    uml: UMLInstance
    log: list[str]

    def setup(self) -> None:
        self.add_report_section(
            when="log",
            key=f"{self.uml} UML",
            content="\n".join(self.log),
        )
        pytest.fail(
            reason=f"WARNING emitted in {self.uml}.",
            pytrace=False,
        )


class ResultStreamHost:
    def __init__(self, config: pytest.Config, uml: UMLInstance, nodeids: list[str]):
        self.config = config
        self.uml = uml
        self.worker = Worker(str(uml))
        self.notrun = nodeids
        self.failed = False

    def logstart(self, nodeid: str, location: tuple) -> None:
        self.config.hook.pytest_runtest_logstart(nodeid=nodeid, location=location)

    def logfinish(self, nodeid: str, location: tuple) -> None:
        self.notrun.remove(next(n for n in self.notrun if n.endswith(nodeid)))
        self.config.hook.pytest_runtest_logfinish(nodeid=nodeid, location=location)

    def logreport(self, data: dict) -> None:
        report = self.config.hook.pytest_report_from_serializable(
            config=self.config, data=data
        )

        report.node = self.worker

        if report.failed:
            self.failed = True

            log = LogParser(self.uml.umllog).get_testcase_log(report.nodeid)
            if log:
                report.sections.append((f"[{self.uml}] UML", "\n".join(log)))
            log = LogParser(self.uml.backendlog).get_testcase_log(report.nodeid)
            if log:
                report.sections.append((f"[{self.uml}] Backend", "\n".join(log)))

        self.config.hook.pytest_runtest_logreport(report=report)


class HostPlugin:
    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        self.args = RunnerArgs.from_namespace(config.option)
        self.notrunids: list[str] = []
        self.extra_cmdline_args = []

        # This should probably be replaced with some generical method to
        # pass along cmdline options
        if config.getoption("runxfail"):
            self.extra_cmdline_args.append("--runxfail")

        print(self.args)

        # https://github.com/pytest-dev/pytest/issues/9316
        reports = config.pluginmanager.get_plugin("reports")
        if reports is not None:
            reports.getworkerinfoline = getworkerinfoline

    def split_tests(
        self, tests: list[pytest.Function]
    ) -> Iterator[tuple[list[pytest.Function], devicetree.FragmentManager]]:
        group: list[pytest.Function] = []
        fragman = devicetree.FragmentManager()
        perjob = 0
        maxperjob = (
            self.args.tests_per_job
            if self.args.tests_per_job
            else max(20, len(tests) / self.args.parallel)
        )

        for test in tests:
            module = inspect.getmodule(test.function)
            run_separately = getattr(module, "run_separately", False)
            dts = getattr(module, "dts", None)

            if run_separately and group:
                yield group, fragman
                perjob = 0
                group = []
                fragman = devicetree.FragmentManager()

            try:
                if dts := getattr(module, "dts", None):
                    fragman.assign(dts)
                group.append(test)

                if not run_separately:
                    perjob += 1
                    if perjob < maxperjob:
                        continue
            except StopIteration:
                pass

            yield group, fragman

            group = []
            if perjob < maxperjob:
                fragman = devicetree.FragmentManager()
            perjob = 0

        if group:
            yield group, fragman

    @pytest.hookimpl()
    def pytest_runtestloop(self, session: pytest.Session) -> Any:
        if session.config.option.collectonly:
            return True

        instance = 0
        local = []
        remote = []

        for item in session.items:
            assert isinstance(item, pytest.Function)

            module = inspect.getmodule(item.function)
            try:
                getattr(module, "dts")
                remote.append(item)
            except AttributeError:
                local.append(item)

        for i, item in enumerate(local):
            nextitem = local[i + 1] if i + 1 < len(local) else None
            self.config.hook.pytest_runtest_protocol(item=item, nextitem=nextitem)

        tr = session.config.pluginmanager.getplugin("terminalreporter")
        write_line = getattr(tr, "write_line", print)

        todo: deque[UMLInstance] = deque()
        results = []
        for group, fragman in self.split_tests(remote):
            workdir = self.args.work_dir / str(instance)

            os.makedirs(workdir, exist_ok=True)

            devicetree.compile(
                src="\n".join(fragman.fragments),
                dtb="test.dtb",
                workdir=workdir,
                ksrcdir=self.args.ksrc_dir,
            )

            testinfos = []
            nodeids = []
            for t in group:
                id = t.nodeid
                nodeids.append(id)

                module = inspect.getmodule(t.function)
                dts = getattr(module, "dts", None)
                res = dts.save_resources() if dts else {}
                info = {"id": id, "resources": res}
                testinfos.append(info)

            info = {
                "tests": testinfos,
                "extra_cmdline_args": self.extra_cmdline_args,
            }

            with (workdir / "tests.json").open("w") as f:
                json.dump(info, f)

            uml = UMLInstance(
                id=instance,
                workdir=workdir,
                runner_args=self.args,
            )

            results.append(
                ResultStreamHost(config=self.config, uml=uml, nodeids=nodeids)
            )

            todo.append(uml)
            instance += 1

        maxactive = self.args.parallel
        active: list[UMLInstance] = []
        done = []
        try:
            while True:
                now = datetime.now()
                for uml in active:
                    uml.resultstream.process({"result": results[uml.id]})

                    if (
                        uml.proc is not None
                        and uml.proc.poll() is not None
                        or (
                            self.args.timeout
                            and (
                                (now - uml.start_time).total_seconds()
                                >= self.args.timeout
                            )
                        )
                    ):
                        uml.stop()
                        active.remove(uml)
                        done.append(uml)

                while todo and len(active) < maxactive:
                    uml = todo.popleft()
                    write_line(f"[{uml}] Starting target...")
                    uml.run()
                    active.append(uml)

                if not todo and not active:
                    break

                time.sleep(0.100)
        finally:
            for uml in active:
                uml.stop()

        for uml in active + done:
            uml.resultstream.process({"result": results[uml.id]})

        incomplete = [r for r in results if r.notrun]
        for r in incomplete:
            r.failed = True
            uml = r.uml
            item = TargetCrashItem.from_parent(
                parent=session, name=f"{uml} crashed/hanged"
            )
            setattr(item, "uml", uml)
            self.config.hook.pytest_runtest_protocol(
                item=item,
                nextitem=None,
            )

        # Some debugging options such as lockdep emit WARNINGs but do not respect
        # panic_on_warn.  Check for any WARNINGS and fail the run unless it's
        # already failed (possibly for some other reason).
        for r in results:
            if r.failed:
                continue

            uml = r.uml
            parser = LogParser(uml.umllog)
            for line, log in parser.get_warning_logs():
                item = WarningItem.from_parent(parent=session, name=f"{uml} {line}")
                setattr(item, "uml", uml)
                setattr(item, "log", log)
                self.config.hook.pytest_runtest_protocol(
                    item=item,
                    nextitem=None,
                )

        return True


def pytest_configure(config: pytest.Config) -> None:
    config.pluginmanager.register(HostPlugin(config), "roadtest-local")


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("roadtest")

    self_dir = Path(__file__).parent.resolve()
    ksrc_dir = Path(
        str(self_dir).removesuffix("/tools/testing/roadtest/roadtest/pytest")
    )
    assert self_dir != ksrc_dir

    build_dir = ksrc_dir / ".roadtest"
    work_dir = ksrc_dir / ".roadtest" / "roadtest-work"

    group.addoption("--arch", default="um")
    group.addoption("--rt-ksrc-dir", type=Path, default=ksrc_dir)
    group.addoption("--rt-work-dir", type=Path, default=work_dir)
    group.addoption("--rt-build-dir", type=Path, default=build_dir)
    group.addoption("--rt-parallel", type=int, default=1)
    group.addoption("--rt-tests-per-job", type=int, default=0)
    group.addoption(
        "--rt-bootargs",
        nargs="*",
        default=[],
        help="Extra arguments to append to the kernel command line (example: trace_event=i2c:* tp_printk)",
    )
    group.addoption(
        "--rt-gdb",
        nargs="?",
        default=None,
        const=1234,
        help="Start a gdbserver for the kernel on the specified port (default: 1234)",
    )

    group.addoption(
        "--rt-timeout",
        type=int,
        default=60,
        help="Timeout (in seconds) for each UML run, 0 to disable",
    )
    group.addoption("--rt-shell", action="store_true")
