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
	char kernelname[128];
	struct miscdevice misc;
	struct miscdevice kernelmisc;
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

static int vhost_kernel_open(struct inode *inode, struct file *file)
{
	struct miscdevice *misc = file->private_data;
	struct vhost *vhost = container_of(misc, struct vhost, kernelmisc);
	struct vhost_dev *dev;

	dev = vhost->ops->open(vhost);
	if (IS_ERR(dev))
		return PTR_ERR(dev);

	dev->vhost = vhost;
	dev->file = file;
	dev->kernel = true;
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
	long ret;

	mutex_lock(&dev->mutex);
	ret = vhost->ops->ioctl(dev, ioctl, arg);
	mutex_unlock(&dev->mutex);

	return ret;
}

static long vhost_kernel_ioctl(struct file *file, unsigned int ioctl, unsigned long arg)
{
	struct vhost_dev *dev = file->private_data;
	struct vhost *vhost = dev->vhost;
	long ret;

	/* Only the kernel is allowed to control virtqueue attributes */
	switch (ioctl) {
	case VHOST_SET_VRING_NUM:
	case VHOST_SET_VRING_ADDR:
	case VHOST_SET_VRING_BASE:
	case VHOST_SET_VRING_ENDIAN:
	case VHOST_SET_MEM_TABLE:
	case VHOST_SET_LOG_BASE:
	case VHOST_SET_LOG_FD:
		return -EPERM;
	}

	mutex_lock(&dev->mutex);

	/*
	 * Userspace should perform all reqired setup on the vhost device
	 * _before_ asking the kernel to start using it.
	 *
	 * Note that ->kernel_attached is never reset, if userspace wants to
	 * attach again it should open the device again.
	 */
	if (dev->kernel_attached) {
		ret = -EPERM;
		goto out_unlock;
	}

	ret = vhost->ops->ioctl(dev, ioctl, arg);

out_unlock:
	mutex_unlock(&dev->mutex);

	return ret;
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

static const struct file_operations vhost_kernel_fops = {
	.owner          = THIS_MODULE,
	.open           = vhost_kernel_open,
	.release        = vhost_release,
	.llseek		= noop_llseek,
	.unlocked_ioctl = vhost_kernel_ioctl,
	.compat_ioctl   = compat_ptr_ioctl,
};

static void vhost_dev_lock_vqs(struct vhost_dev *d)
{
	int i;

	for (i = 0; i < d->nvqs; ++i)
		mutex_lock_nested(&d->vqs[i]->mutex, i);
}

static void vhost_dev_unlock_vqs(struct vhost_dev *d)
{
	int i;

	for (i = 0; i < d->nvqs; ++i)
		mutex_unlock(&d->vqs[i]->mutex);
}

struct vhost_dev *vhost_dev_get(int fd)
{
	struct file *file;
	struct vhost_dev *dev;
	struct vhost_dev *ret;
	int err;
	int i;

	file = fget(fd);
	if (!file)
		return ERR_PTR(-EBADF);

	if (file->f_op != &vhost_kernel_fops) {
		ret = ERR_PTR(-EINVAL);
		goto err_fput;
	}

	dev = file->private_data;

	mutex_lock(&dev->mutex);
	vhost_dev_lock_vqs(dev);

	err = vhost_dev_check_owner(dev);
	if (err) {
		ret = ERR_PTR(err);
		goto err_unlock;
	}

	if (dev->kernel_attached) {
		ret = ERR_PTR(-EBUSY);
		goto err_unlock;
	}

	if (!dev->iotlb) {
		ret = ERR_PTR(-EINVAL);
		goto err_unlock;
	}

	for (i = 0; i < dev->nvqs; i++) {
		struct vhost_virtqueue *vq = dev->vqs[i];

		if (vq->private_data) {
			ret = ERR_PTR(-EBUSY);
			goto err_unlock;
		}
	}

	dev->kernel_attached = true;

	vhost_dev_unlock_vqs(dev);
	mutex_unlock(&dev->mutex);

	return dev;

err_unlock:
	vhost_dev_unlock_vqs(dev);
	mutex_unlock(&dev->mutex);
err_fput:
	fput(file);
	return ret;
}
EXPORT_SYMBOL_GPL(vhost_dev_get);

void vhost_dev_start_vq(struct vhost_dev *dev, u16 idx)
{
	struct vhost *vhost = dev->vhost;

	mutex_lock(&dev->mutex);
	vhost->ops->start_vq(dev, idx);
	mutex_unlock(&dev->mutex);
}
EXPORT_SYMBOL_GPL(vhost_dev_start_vq);

void vhost_dev_stop_vq(struct vhost_dev *dev, u16 idx)
{
	struct vhost *vhost = dev->vhost;

	mutex_lock(&dev->mutex);
	vhost->ops->stop_vq(dev, idx);
	mutex_unlock(&dev->mutex);
}
EXPORT_SYMBOL_GPL(vhost_dev_stop_vq);

void vhost_dev_put(struct vhost_dev *dev)
{
	/* The virtqueues should already be stopped. */
	fput(dev->file);
}
EXPORT_SYMBOL_GPL(vhost_dev_put);

static bool vhost_kernel_supported(const struct vhost_ops *ops)
{
	if (!IS_ENABLED(CONFIG_VHOST_KERNEL))
		return false;

	return ops->start_vq && ops->stop_vq;
}

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

	if (vhost_kernel_supported(ops)) {
		snprintf(vhost->kernelname, sizeof(vhost->kernelname),
			 "%s-kernel", ops->name);

		vhost->kernelmisc.minor = MISC_DYNAMIC_MINOR;
		vhost->kernelmisc.name = vhost->kernelname;
		vhost->kernelmisc.fops = &vhost_kernel_fops;

		ret = misc_register(&vhost->kernelmisc);
		if (ret) {
			misc_deregister(&vhost->misc);
			kfree(vhost);
			return ERR_PTR(ret);
		}
	}

	return vhost;
}
EXPORT_SYMBOL_GPL(vhost_register);

void vhost_unregister(struct vhost *vhost)
{
	if (vhost_kernel_supported(vhost->ops))
		misc_deregister(&vhost->kernelmisc);
	misc_deregister(&vhost->misc);
	kfree(vhost);
}
EXPORT_SYMBOL_GPL(vhost_unregister);

MODULE_LICENSE("GPL v2");
