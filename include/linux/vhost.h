/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _INCLUDE_LINUX_VHOST_H
#define _INCLUDE_LINUX_VHOST_H

#include <uapi/linux/vhost.h>

struct vhost_dev;

struct vhost_dev *vhost_dev_get(int fd);
void vhost_dev_put(struct vhost_dev *dev);

int vhost_dev_set_vring_num(struct vhost_dev *dev, unsigned int idx,
			    unsigned int num);
int vhost_dev_set_num_addr(struct vhost_dev *dev, unsigned int idx, void *desc,
			   void *avail, void *used);

void vhost_dev_start_vq(struct vhost_dev *dev, u16 idx);
void vhost_dev_stop_vq(struct vhost_dev *dev, u16 idx);

int vhost_dev_iotlb_update(struct vhost_dev *dev, u64 iova, u64 size,
			   u64 kaddr, unsigned int perm);

#endif
