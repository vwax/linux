#!/bin/sh -ex
# SPDX-License-Identifier: GPL-2.0-only

cleanup() {
	[ -z "$PID" ] || kill $PID 2>/dev/null || :
	[ -z "$PINGPID0" ] || kill $PINGPID0 2>/dev/null || :
	[ -z "$PINGPID1" ] || kill $PINGPID1 2>/dev/null || :
	ip netns del g2h 2>/dev/null || :
	ip netns del h2g 2>/dev/null || :
}

fail() {
	echo "FAIL: $*"
	exit 1
}

./vhost_kernel_test || fail "Sanity test failed"

cleanup
trap cleanup EXIT

test_one() {
	ls /sys/class/net/ > before
	echo > new

	./vhost_kernel_test --serve &
	PID=$!

	echo 'Waiting for interfaces'

	timeout=5
	while [ $timeout -gt 0 ]; do
		timeout=$(($timeout - 1))
		sleep 1
		ls /sys/class/net/ > after
		grep -F -x -v -f before after > new || continue
		[ $(wc -l < new) -eq 2 ] || continue
		break
	done

	g2h=
	h2g=

	while IFS= read -r iface; do
		case $iface in
			vhostkernel*)
				h2g=$iface
				;;
			*)
				# Assumed to be virtio-net
				g2h=$iface
				;;
		esac

	done<new

	[ "$g2h" ] || fail "Did not find guest-to-host interface"
	[ "$h2g" ] || fail "Did not find host-to-guest interface"

	# IPv6 link-local addresses prevent short-circuit delivery.
	hostip=fe80::0
	guestip=fe80::1

	# Move the interfaces out of the default namespaces to prevent network manager
	# daemons from messing with them.
	ip netns add g2h
	ip netns add h2g

	ip link set dev $h2g netns h2g
	ip netns exec h2g ip addr add dev $h2g scope link $hostip
	ip netns exec h2g ip link set dev $h2g up

	ip link set dev $g2h netns g2h
	ip netns exec g2h ip addr add dev $g2h scope link $guestip
	ip netns exec g2h ip link set dev $g2h up

	# ip netns exec g2h tcpdump -i $g2h -w $g2h.pcap &
	# ip netns exec h2g tcpdump -i $h2g -w $h2g.pcap &

	ip netns exec h2g ping6 -c10 -A -s 20000 $guestip%$h2g
	ip netns exec g2h ping6 -c10 -A -s 20000 $hostip%$g2h
}

start_background_flood() {
	ip netns exec h2g ping6 -f $guestip%$h2g &
	PINGPID0=$!
	ip netns exec g2h ping6 -f $hostip%$g2h &
	PINGPID1=$!
	sleep 1
}

echo TEST: Basic test
test_one
# Trigger cleanup races
start_background_flood
cleanup

echo TEST: Close vhost_test fd before vhost
test_one
start_background_flood
kill -USR1 $PID
PID=
cleanup

echo TEST: Unbind virtio_net and close
test_one
start_background_flood
echo virtio0 > /sys/bus/virtio/drivers/virtio_net/unbind
cleanup

echo TEST: Unbind and rebind virtio_net
test_one
start_background_flood
echo virtio0 > /sys/bus/virtio/drivers/virtio_net/unbind
echo virtio0 > /sys/bus/virtio/drivers/virtio_net/bind
# We assume that $g2h is the same after the new probe
ip link set dev $g2h netns g2h
ip netns exec g2h ip addr add dev $g2h scope link $guestip
ip netns exec g2h ip link set dev $g2h up
ip netns exec g2h ping6 -c10 -A -s 20000 $hostip%$g2h
cleanup

trap - EXIT

echo OK
