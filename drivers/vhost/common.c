// SPDX-License-Identifier: GPL-2.0-only
#include <linux/eventfd.h>
#include <linux/vhost.h>
#include <linux/uio.h>
#include <linux/mm.h>
#include <linux/miscdevice.h>
#include <linux/mutex.h>
#include <linux/poll.h>
#include <linux/file.h>
#include <linux/highmem.h>
#include <linux/slab.h>
#include <linux/vmalloc.h>
#include <linux/kthread.h>
#include <linux/cgroup.h>
#include <linux/module.h>
#include <linux/sort.h>
#include <linux/sched/mm.h>
#include <linux/sched/signal.h>
#include <linux/interval_tree_generic.h>
#include <linux/nospec.h>
#include <linux/kcov.h>

#include "vhost.h"

struct vhost_ops;

struct vhost {
	struct miscdevice misc;
	const struct vhost_ops *ops;
};

static int vhost_open(struct inode *inode, struct file *file)
{
	struct miscdevice *misc = file->private_data;
	struct vhost *vhost = container_of(misc, struct vhost, misc);
	struct vhost_dev *dev;

	dev = vhost->ops->open(vhost);
	if (IS_ERR(dev))
		return PTR_ERR(dev);

	dev->vhost = vhost;
	dev->file = file;
	file->private_data = dev;

	return 0;
}

static int vhost_release(struct inode *inode, struct file *file)
{
	struct vhost_dev *dev = file->private_data;
	struct vhost *vhost = dev->vhost;

	vhost->ops->release(dev);

	return 0;
}

static long vhost_ioctl(struct file *file, unsigned int ioctl, unsigned long arg)
{
	struct vhost_dev *dev = file->private_data;
	struct vhost *vhost = dev->vhost;

	return vhost->ops->ioctl(dev, ioctl, arg);
}

static ssize_t vhost_read_iter(struct kiocb *iocb, struct iov_iter *to)
{
	struct file *file = iocb->ki_filp;
	struct vhost_dev *dev = file->private_data;
	int noblock = file->f_flags & O_NONBLOCK;

	return vhost_chr_read_iter(dev, to, noblock);
}

static ssize_t vhost_write_iter(struct kiocb *iocb, struct iov_iter *from)
{
	struct file *file = iocb->ki_filp;
	struct vhost_dev *dev = file->private_data;

	return vhost_chr_write_iter(dev, from);
}

static __poll_t vhost_poll(struct file *file, poll_table *wait)
{
	struct vhost_dev *dev = file->private_data;

	return vhost_chr_poll(file, dev, wait);
}

static const struct file_operations vhost_fops = {
	.owner          = THIS_MODULE,
	.open           = vhost_open,
	.release        = vhost_release,
	.llseek		= noop_llseek,
	.unlocked_ioctl = vhost_ioctl,
	.compat_ioctl   = compat_ptr_ioctl,
	.read_iter      = vhost_read_iter,
	.write_iter     = vhost_write_iter,
	.poll           = vhost_poll,
};

struct vhost *vhost_register(const struct vhost_ops *ops)
{
	struct vhost *vhost;
	int ret;

	vhost = kzalloc(sizeof(*vhost), GFP_KERNEL);
	if (!vhost)
		return ERR_PTR(-ENOMEM);

	vhost->misc.minor = ops->minor;
	vhost->misc.name = ops->name;
	vhost->misc.fops = &vhost_fops;
	vhost->ops = ops;

	ret = misc_register(&vhost->misc);
	if (ret) {
		kfree(vhost);
		return ERR_PTR(ret);
	}

	return vhost;
}
EXPORT_SYMBOL_GPL(vhost_register);

void vhost_unregister(struct vhost *vhost)
{
	misc_deregister(&vhost->misc);
	kfree(vhost);
}
EXPORT_SYMBOL_GPL(vhost_unregister);

MODULE_LICENSE("GPL v2");
