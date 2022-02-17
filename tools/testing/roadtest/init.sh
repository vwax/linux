#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only

mount -t proc proc /proc
echo 8 > /proc/sys/kernel/printk
mount -t sysfs nodev /sys
mount -t debugfs nodev /sys/kernel/debug

echo 0 > /sys/bus/i2c/drivers_autoprobe
echo 0 > /sys/bus/platform/drivers_autoprobe

python3 -m roadtest.cmd.remote
status=$?
[ "${ROADTEST_SHELL}" = "1" ] || {
    # rsync doesn't handle these zero-sized files correctly.
    cp -ra --no-preserve=ownership /sys/kernel/debug/gcov ${ROADTEST_WORK_DIR}/gcov
    echo o > /proc/sysrq-trigger
}
exec setsid sh -c 'exec bash </dev/tty0 >/dev/tty0 2>&1'
