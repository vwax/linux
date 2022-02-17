# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import argparse
import fnmatch
import sys
import unittest
from typing import Optional
from unittest.suite import TestSuite

assert sys.version_info >= (3, 9), "Python version is too old"

from roadtest.core.suite import UMLSuite, UMLTestCase


def make_umlsuite(args: argparse.Namespace) -> UMLSuite:
    return UMLSuite(
        timeout=args.timeout,
        workdir=args.work_dir,
        builddir=args.build_dir,
        ksrcdir=args.ksrc_dir,
        uml_args_pre=args.uml_prepend,
        uml_args_post=args.uml_append,
        shell=args.shell,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout (in seconds) for each UML run, 0 to disable",
    )
    parser.add_argument("--work-dir", type=str, help="Work directory for UML runs")
    parser.add_argument("--build-dir", type=str, required=True)
    parser.add_argument("--ksrc-dir", type=str, required=True)
    parser.add_argument(
        "--uml-prepend",
        nargs="*",
        default=[],
        help="Extra arguments to prepend to the UML command (example: gdbserver :1234)",
    )
    parser.add_argument(
        "--uml-append",
        nargs="*",
        default=[],
        help="Extra arguments to append to the UML command (example: trace_event=i2c:* tp_printk)",
    )
    parser.add_argument(
        "--filter",
        nargs="+",
        default=[],
    )
    parser.add_argument("--shell", action="store_true")
    parser.add_argument("test", nargs="?", default="roadtest")
    args = parser.parse_args()

    if args.shell:
        args.timeout = 0

        if not any(p.startswith("con=") for p in args.uml_append):
            print(
                "Error: --shell used but no con= UML argument specified",
                file=sys.stderr,
            )
            sys.exit(1)

    test = args.test
    test = test.replace("/", ".")
    test = test.removesuffix(".py")
    test = test.removesuffix(".")

    loader = unittest.defaultTestLoader
    suitegroups = loader.discover(test)

    args.filter = [f"*{f}*" for f in args.filter]

    # Backend tests and the like don't need to be run inside UML.
    localsuite = None

    # For simplicity, we currently run all target tests in one UML instance
    # since python in UML is slow to start up.  This can be revisited if we
    # want to run several UML instances in parallel.
    deftargetsuite = None
    targetsuites = []

    for suites in suitegroups:
        # unittest can in arbitrarily nest and mix TestCases
        # and TestSuites, but we expect a fixed hierarchy.
        assert isinstance(suites, unittest.TestSuite)

        for suite in suites:
            # assert not isinstance(suite, unittest.TestCase)

            # If the import of a test fails, then suite is a
            # unittest.loader._FailedTest instead of a suite
            if not isinstance(suite, unittest.TestSuite):
                suite = [suite]  # type: ignore[assignment]

            # Suite at this level contains one TestCase for each
            # test method in a particular test class.
            #
            # All the test functions for one particular test class
            # can only be run either in UML or locally, not mixed.
            destsuite: Optional[TestSuite] = None

            for t in suite:  # type: ignore[union-attr]
                # We don't support suites nested at this level.
                assert isinstance(t, unittest.TestCase)

                id = t.id()
                if args.filter and not any(fnmatch.fnmatch(id, f) for f in args.filter):
                    continue

                if isinstance(t, UMLTestCase):
                    if t.run_separately:
                        if not destsuite:
                            destsuite = make_umlsuite(args)
                            targetsuites.append(destsuite)
                    else:
                        if not deftargetsuite:
                            deftargetsuite = make_umlsuite(args)
                            targetsuites.append(deftargetsuite)

                        destsuite = deftargetsuite
                else:
                    if not localsuite:
                        localsuite = TestSuite()
                    destsuite = localsuite

                if destsuite:
                    destsuite.addTest(t)

    tests = unittest.TestSuite()
    if localsuite:
        tests.addTest(localsuite)
    tests.addTests(targetsuites)

    result = unittest.TextTestRunner(verbosity=2).run(tests)
    sys.exit(not result.wasSuccessful())


if __name__ == "__main__":
    main()
