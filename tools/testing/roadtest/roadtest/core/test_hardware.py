# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

from pathlib import Path
from typing import Any

import pytest

from roadtest.backend.mock import MockBackend
from roadtest.core.hardware import Hardware


def test_mock(tmp_path: Path) -> None:
    backend = MockBackend(tmp_path)
    hw = Hardware[Any](bus="dummy", work=tmp_path)

    backend.reg_write(0x1, 0xDEAD)
    backend.reg_write(0x2, 0xBEEF)
    mock = hw.update_mock()
    mock.assert_reg_write_once(0x1, 0xDEAD)

    backend.reg_write(0x1, 0xCAFE)
    hw.update_mock(mock)
    with pytest.raises(AssertionError):
        mock.assert_reg_write_once(0x1, 0xDEAD)

    mock.assert_last_reg_write(0x1, 0xCAFE)
    mock.assert_last_reg_write_mask(0x1, mask=0xFF, value=0xFE)
    mock.assert_last_reg_set_mask(0x1, mask=0x2)
    mock.assert_last_reg_clear_mask(0x1, mask=0x1)

    assert mock.get_last_reg_write(0x1) == 0xCAFE
    assert mock.get_last_reg_write(0x2) == 0xBEEF

    with pytest.raises(AssertionError):
        assert mock.get_last_reg_write(0x3) == 0x0

    mock.reset_mock()
    with pytest.raises(AssertionError):
        mock.assert_last_reg_write(0x2, 0xBEEF)
