# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import functools
from pathlib import Path
from typing import Any, Callable

from roadtest.core.opslog import OpsLogWriter


class MockBackend:
    def __init__(self, work: Path) -> None:
        self.opslog = OpsLogWriter(work)

    @functools.cache
    def __getattr__(self, name: str) -> Callable:
        def func(*args: Any, **kwargs: Any) -> None:
            self.opslog.write(f"mock.{name}(*{str(args)}, **{str(kwargs)})")

        return func
