// SPDX-License-Identifier: GPL-2.0-only
#define _GNU_SOURCE
#include <err.h>
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <linux/if_tun.h>
#include <linux/virtio_net.h>
#include <linux/vhost.h>
#include <net/if.h>
#include <netdb.h>
#include <netinet/in.h>
#include <stdio.h>
#include <string.h>
#include <signal.h>
#include <stdbool.h>
#include <stdlib.h>
#include <sys/eventfd.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#ifndef VIRTIO_F_ACCESS_PLATFORM
#define VIRTIO_F_ACCESS_PLATFORM 33
#endif

#ifndef VKTEST_ATTACH_VHOST
#define VKTEST_ATTACH_VHOST _IOW(0xbf, 0x31, int)
#endif

static int vktest;
static const int num_vqs = 2;

static int tun_alloc(char *dev)
{
	int hdrsize = sizeof(struct virtio_net_hdr_mrg_rxbuf);
	struct ifreq ifr = {
		.ifr_flags = IFF_TAP | IFF_NO_PI | IFF_VNET_HDR,
	};
	int fd, ret;

	fd = open("/dev/net/tun", O_RDWR);
	if (fd < 0)
		err(1, "open /dev/net/tun");

	strncpy(ifr.ifr_name, dev, IFNAMSIZ);

	ret = ioctl(fd, TUNSETIFF, &ifr);
	if (ret < 0)
		err(1, "TUNSETIFF");

	ret = ioctl(fd, TUNSETOFFLOAD,
		    TUN_F_CSUM | TUN_F_TSO4 | TUN_F_TSO6 | TUN_F_TSO_ECN);
	if (ret < 0)
		err(1, "TUNSETOFFLOAD");

	ret = ioctl(fd, TUNSETVNETHDRSZ, &hdrsize);
	if (ret < 0)
		err(1, "TUNSETVNETHDRSZ");

	strncpy(dev, ifr.ifr_name, IFNAMSIZ);

	return fd;
}

static void handle_signal(int signum)
{
	if (signum == SIGUSR1)
		close(vktest);
}

static void vhost_net_set_backend(int vhost)
{
	char if_name[IFNAMSIZ];
	int tap_fd;

	snprintf(if_name, IFNAMSIZ, "vhostkernel%d", 0);

	tap_fd = tun_alloc(if_name);

	for (int i = 0; i < num_vqs; i++) {
		struct vhost_vring_file txbackend = {
			.index = i,
			.fd = tap_fd,
		};
		int ret;

		ret = ioctl(vhost, VHOST_NET_SET_BACKEND, &txbackend);
		if (ret < 0)
			err(1, "VHOST_NET_SET_BACKEND");
	}
}

static void prepare_vhost_vktest(int vhost, int vktest)
{
	uint64_t features = 1llu << VIRTIO_F_ACCESS_PLATFORM | 1llu << VIRTIO_F_VERSION_1;
	int ret;

	for (int i = 0; i < num_vqs; i++) {
		int kickfd = eventfd(0, EFD_CLOEXEC);

		if (kickfd < 0)
			err(1, "eventfd");

		struct vhost_vring_file kick = {
			.index = i,
			.fd = kickfd,
		};

		ret = ioctl(vktest, VHOST_SET_VRING_KICK, &kick);
		if (ret < 0)
			err(1, "VHOST_SET_VRING_KICK");

		ret = ioctl(vhost, VHOST_SET_VRING_KICK, &kick);
		if (ret < 0)
			err(1, "VHOST_SET_VRING_KICK");
	}

	for (int i = 0; i < num_vqs; i++) {
		int callfd = eventfd(0, EFD_CLOEXEC);

		if (callfd < 0)
			err(1, "eventfd");

		struct vhost_vring_file call = {
			.index = i,
			.fd = callfd,
		};

		ret = ioctl(vktest, VHOST_SET_VRING_CALL, &call);
		if (ret < 0)
			err(1, "VHOST_SET_VRING_CALL");

		ret = ioctl(vhost, VHOST_SET_VRING_CALL, &call);
		if (ret < 0)
			err(1, "VHOST_SET_VRING_CALL");
	}

	ret = ioctl(vhost, VHOST_SET_FEATURES, &features);
	if (ret < 0)
		err(1, "VHOST_SET_FEATURES");
}

static void test_attach(void)
{
	int vktest, vktest2;
	int vhost;
	int ret;

	vhost = open("/dev/vhost-net-kernel", O_RDONLY);
	if (vhost < 0)
		err(1, "vhost");

	vktest = open("/dev/vktest", O_RDONLY);
	if (vktest < 0)
		err(1, "vhost");

	ret = ioctl(vhost, VHOST_SET_OWNER);
	if (ret < 0)
		err(1, "VHOST_SET_OWNER");

	prepare_vhost_vktest(vhost, vktest);

	ret = ioctl(vktest, VKTEST_ATTACH_VHOST, vhost);
	if (ret < 0)
		err(1, "VKTEST_ATTACH_VHOST");

	vktest2 = open("/dev/vktest", O_RDONLY);
	if (vktest2 < 0)
		err(1, "vktest");

	ret = ioctl(vktest2, VKTEST_ATTACH_VHOST, vhost);
	if (ret == 0)
		errx(1, "Second attach did not fail");

	close(vktest2);
	close(vktest);
	close(vhost);
}

int main(int argc, char *argv[])
{
	bool serve = false;
	uint64_t features;
	int vhost;
	struct option options[] = {
		{ "serve", no_argument, NULL, 's' },
		{}
	};

	while (1) {
		int c;

		c = getopt_long_only(argc, argv, "", options, NULL);
		if (c == -1)
			break;

		switch (c) {
		case 's':
			serve = true;
			break;
		case '?':
		default:
			errx(1, "usage %s [--serve]", argv[0]);
		}
	};

	if (!serve) {
		test_attach();
		return 0;
	}

	vhost = open("/dev/vhost-net-kernel", O_RDONLY);
	if (vhost < 0)
		err(1, "vhost");

	int ret;

	ret = ioctl(vhost, VHOST_SET_OWNER);
	if (ret < 0)
		err(1, "VHOST_SET_OWNER");

	vktest = open("/dev/vktest", O_RDONLY);
	if (vktest < 0)
		err(1, "vktest");

	for (int i = 0; i < num_vqs; i++) {
		int kickfd;

		kickfd = eventfd(0, EFD_CLOEXEC);
		if (kickfd < 0)
			err(1, "eventfd");

		struct vhost_vring_file kick = {
			.index = i,
			.fd = kickfd,
		};

		ret = ioctl(vktest, VHOST_SET_VRING_KICK, &kick);
		if (ret < 0)
			err(1, "VHOST_SET_VRING_KICK");

		ret = ioctl(vhost, VHOST_SET_VRING_KICK, &kick);
		if (ret < 0)
			err(1, "VHOST_SET_VRING_KICK");
	}

	for (int i = 0; i < num_vqs; i++) {
		int callfd;

		callfd = eventfd(0, EFD_CLOEXEC);
		if (callfd < 0)
			err(1, "eventfd");

		struct vhost_vring_file call = {
			.index = i,
			.fd = callfd,
		};

		ret = ioctl(vktest, VHOST_SET_VRING_CALL, &call);
		if (ret < 0)
			err(1, "VHOST_SET_VRING_CALL");

		ret = ioctl(vhost, VHOST_SET_VRING_CALL, &call);
		if (ret < 0)
			err(1, "VHOST_SET_VRING_CALL");
	}

	features = 1llu << VIRTIO_F_ACCESS_PLATFORM | 1llu << VIRTIO_F_VERSION_1;
	ret = ioctl(vhost, VHOST_SET_FEATURES, &features);
	if (ret < 0)
		err(1, "VHOST_SET_FEATURES");

	vhost_net_set_backend(vhost);

	ret = ioctl(vktest, VKTEST_ATTACH_VHOST, vhost);
	if (ret < 0)
		err(1, "VKTEST_ATTACH_VHOST");

	signal(SIGUSR1, handle_signal);

	while (1)
		pause();

	return 0;
}
