# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

import logging

import roadtest.backend.backend

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s: %(message)s", level=logging.DEBUG
)

backend = roadtest.backend.backend.Backend()
backend.process_control()
