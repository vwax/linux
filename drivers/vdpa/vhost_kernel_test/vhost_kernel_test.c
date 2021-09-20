// SPDX-License-Identifier: GPL-2.0-only

#define pr_fmt(fmt) "%s:%s: " fmt, KBUILD_MODNAME, __func__
#include <linux/interrupt.h>
#include <linux/module.h>
#include <linux/vdpa.h>
#include <linux/vhost.h>
#include <linux/virtio.h>
#include <linux/virtio_config.h>
#include <linux/virtio_ring.h>
#include <linux/eventfd.h>
#include <linux/dma-mapping.h>
#include <linux/dma-map-ops.h>
#include <linux/miscdevice.h>
#include <linux/slab.h>
#include <linux/wait.h>
#include <linux/poll.h>
#include <linux/file.h>
#include <linux/irq_work.h>
#include <uapi/linux/virtio_ids.h>
#include <uapi/linux/virtio_net.h>
#include <uapi/linux/vhost.h>

struct vktest_vq {
	struct vktest *vktest;
	struct eventfd_ctx *kick;
	struct eventfd_ctx *call;
	u64 desc_addr;
	u64 device_addr;
	u64 driver_addr;
	u32 num;
	bool ready;
	wait_queue_entry_t call_wait;
	wait_queue_head_t *wqh;
	poll_table call_pt;
	struct vdpa_callback cb;
	struct irq_work irq_work;
};

struct vktest {
	struct vdpa_device vdpa;
	struct mutex mutex;
	struct vhost_dev *vhost;
	struct virtio_net_config config;
	struct vktest_vq vqs[2];
	u8 status;
};

static struct vktest *vdpa_to_vktest(struct vdpa_device *vdpa)
{
	return container_of(vdpa, struct vktest, vdpa);
}

static int vktest_set_vq_address(struct vdpa_device *vdpa, u16 idx,
				 u64 desc_area, u64 driver_area,
				 u64 device_area)
{
	struct vktest *vktest = vdpa_to_vktest(vdpa);
	struct vktest_vq *vq = &vktest->vqs[idx];

	vq->desc_addr = desc_area;
	vq->driver_addr = driver_area;
	vq->device_addr = device_area;

	return 0;
}

static void vktest_set_vq_num(struct vdpa_device *vdpa, u16 idx, u32 num)
{
	struct vktest *vktest = vdpa_to_vktest(vdpa);
	struct vktest_vq *vq = &vktest->vqs[idx];

	vq->num = num;
}

static void vktest_kick_vq(struct vdpa_device *vdpa, u16 idx)
{
	struct vktest *vktest = vdpa_to_vktest(vdpa);
	struct vktest_vq *vq = &vktest->vqs[idx];

	if (vq->kick)
		eventfd_signal(vq->kick, 1);
}

static void vktest_set_vq_cb(struct vdpa_device *vdpa, u16 idx,
			     struct vdpa_callback *cb)
{
	struct vktest *vktest = vdpa_to_vktest(vdpa);
	struct vktest_vq *vq = &vktest->vqs[idx];

	vq->cb = *cb;
}

static void vktest_set_vq_ready(struct vdpa_device *vdpa, u16 idx, bool ready)
{
	struct vktest *vktest = vdpa_to_vktest(vdpa);
	struct vktest_vq *vq = &vktest->vqs[idx];
	struct vhost_dev *vhost = vktest->vhost;

	if (!ready) {
		vq->ready = false;
		vhost_dev_stop_vq(vhost, idx);
		return;
	}

	vq->ready = true;
	vhost_dev_set_num_addr(vhost, idx, (void *)vq->desc_addr,
			       (void *)vq->driver_addr,
			       (void *)vq->device_addr);
	vhost_dev_set_vring_num(vhost, idx, vq->num);
	vhost_dev_start_vq(vhost, idx);
}

static bool vktest_get_vq_ready(struct vdpa_device *vdpa, u16 idx)
{
	struct vktest *vktest = vdpa_to_vktest(vdpa);
	struct vktest_vq *vq = &vktest->vqs[idx];

	return vq->ready;
}

static int vktest_set_vq_state(struct vdpa_device *vdpa, u16 idx,
			       const struct vdpa_vq_state *state)
{
	return 0;
}

static int vktest_get_vq_state(struct vdpa_device *vdpa, u16 idx,
			       struct vdpa_vq_state *state)
{
	return 0;
}

static u32 vktest_get_vq_align(struct vdpa_device *vdpa)
{
	return PAGE_SIZE;
}

static u64 vktest_get_features(struct vdpa_device *vdpa)
{
	return 1llu << VIRTIO_F_ACCESS_PLATFORM | 1llu << VIRTIO_F_VERSION_1;
}

static int vktest_set_features(struct vdpa_device *vdpa, u64 features)
{
	return 0;
}

static void vktest_set_config_cb(struct vdpa_device *vdpa,
				 struct vdpa_callback *cb)
{
}

static u16 vktest_get_vq_num_max(struct vdpa_device *vdpa)
{
	return 256;
}

static u32 vktest_get_device_id(struct vdpa_device *vdpa)
{
	return VIRTIO_ID_NET;
}

static u32 vktest_get_vendor_id(struct vdpa_device *vdpa)
{
	return 0;
}

static u8 vktest_get_status(struct vdpa_device *vdpa)
{
	struct vktest *vktest = vdpa_to_vktest(vdpa);

	return vktest->status;
}

static int vktest_reset(struct vdpa_device *vdpa)
{
	struct vktest *vktest = vdpa_to_vktest(vdpa);
	struct vhost_dev *vhost = vktest->vhost;

	if (vhost) {
		int i;

		for (i = 0; i < ARRAY_SIZE(vktest->vqs); i++)
			vhost_dev_stop_vq(vhost, i);
	}

	vktest->status = 0;

	return 0;
}

static void vktest_set_status(struct vdpa_device *vdpa, u8 status)
{
	struct vktest *vktest = vdpa_to_vktest(vdpa);

	vktest->status = status;
}

static size_t vktest_get_config_size(struct vdpa_device *vdpa)
{
	return sizeof(vdpa->config);
}

static void vktest_get_config(struct vdpa_device *vdpa, unsigned int offset,
			      void *buf, unsigned int len)
{
	struct vktest *vktest = vdpa_to_vktest(vdpa);

	if (offset + len > sizeof(vktest->config))
		return;

	memcpy(buf, (void *)&vktest->config + offset, len);
}

static void vktest_set_config(struct vdpa_device *vdpa, unsigned int offset,
			      const void *buf, unsigned int len)
{
}

static void vktest_free(struct vdpa_device *vdpa)
{
	struct vktest *vktest = vdpa_to_vktest(vdpa);
	struct vhost_dev *vhost = vktest->vhost;
	int i;

	for (i = 0; i < ARRAY_SIZE(vktest->vqs); i++) {
		struct vktest_vq *vq = &vktest->vqs[i];

		if (vq->wqh) {
			remove_wait_queue(vq->wqh, &vq->call_wait);
			vq->wqh = NULL;
		}

		irq_work_sync(&vq->irq_work);
	}

	if (vhost)
		vhost_dev_put(vhost);

	for (i = 0; i < ARRAY_SIZE(vktest->vqs); i++) {
		struct vktest_vq *vq = &vktest->vqs[i];

		if (vq->kick)
			eventfd_ctx_put(vq->kick);
		if (vq->call)
			eventfd_ctx_put(vq->call);

		vq->kick = NULL;
		vq->call = NULL;
	}
}

/*
 * By not implementing ->set_dma() and ->dma_map() and by using a dma_dev which is
 * not tied to any hardware we ensure that vhost-vdpa cannot be opened if it
 * binds to this vDPA driver (it will fail in vhost_vdpa_alloc_domain()).  This
 * ensures that only kernel code (virtio-vdpa) will be able to control VQ
 * addresses, etc.
 */
static const struct vdpa_config_ops vktest_config_ops = {
	.set_vq_address 	= vktest_set_vq_address,
	.set_vq_num		= vktest_set_vq_num,
	.kick_vq		= vktest_kick_vq,
	.set_vq_cb		= vktest_set_vq_cb,
	.set_vq_ready		= vktest_set_vq_ready,
	.get_vq_ready		= vktest_get_vq_ready,
	.set_vq_state		= vktest_set_vq_state,
	.get_vq_state		= vktest_get_vq_state,
	.get_vq_align		= vktest_get_vq_align,
	.get_features		= vktest_get_features,
	.set_features		= vktest_set_features,
	.set_config_cb		= vktest_set_config_cb,
	.get_vq_num_max		= vktest_get_vq_num_max,
	.get_device_id		= vktest_get_device_id,
	.get_vendor_id		= vktest_get_vendor_id,
	.get_status		= vktest_get_status,
	.set_status		= vktest_set_status,
	.reset			= vktest_reset,
	.get_config_size 	= vktest_get_config_size,
	.get_config		= vktest_get_config,
	.set_config		= vktest_set_config,
	.free			= vktest_free,
};

static dma_addr_t vktest_map_page(struct device *dev, struct page *page,
				  unsigned long offset, size_t size,
				  enum dma_data_direction dir,
				  unsigned long attrs)
{
	return (dma_addr_t)page_to_virt(page) + offset;
}

static void vktest_unmap_page(struct device *dev, dma_addr_t dma_addr,
			      size_t size, enum dma_data_direction dir,
			      unsigned long attrs)
{
}

static void *vktest_alloc_coherent(struct device *dev, size_t size,
				   dma_addr_t *dma_addr, gfp_t flag,
				   unsigned long attrs)
{
	void *p;

	p = kvmalloc(size, flag);
	if (!p) {
		*dma_addr = DMA_MAPPING_ERROR;
		return NULL;
	}

	*dma_addr = (dma_addr_t)p;

	return p;
}

static void vktest_free_coherent(struct device *dev, size_t size, void *vaddr,
				 dma_addr_t dma_addr, unsigned long attrs)
{
	kvfree(vaddr);
}

static const struct dma_map_ops vktest_dma_ops = {
	.map_page = vktest_map_page,
	.unmap_page = vktest_unmap_page,
	.alloc = vktest_alloc_coherent,
	.free = vktest_free_coherent,
};

static void vktest_call_notify(struct vktest_vq *vq)
{
	struct vdpa_callback *cb = &vq->cb;

	if (cb->callback)
		cb->callback(cb->private);
}

static void do_up_read(struct irq_work *entry)
{
	struct vktest_vq *vq = container_of(entry, struct vktest_vq, irq_work);

	vktest_call_notify(vq);
}

static int vktest_open(struct inode *inode, struct file *file)
{
	struct vktest *vktest;
	struct device *dev;
	int ret = 0;
	int i;

	vktest = vdpa_alloc_device(struct vktest, vdpa, NULL,
				   &vktest_config_ops, NULL, false);
	if (IS_ERR(vktest))
		return PTR_ERR(vktest);

	for (i = 0; i < ARRAY_SIZE(vktest->vqs); i++) {
		struct vktest_vq *vq = &vktest->vqs[i];

		init_irq_work(&vq->irq_work, do_up_read);
	}

	dev = &vktest->vdpa.dev;
	dev->dma_mask = &dev->coherent_dma_mask;
	ret = dma_set_mask_and_coherent(dev, DMA_BIT_MASK(64));
	if (ret)
		goto err_put_device;

	dev->dma_mask = &dev->coherent_dma_mask;
	set_dma_ops(dev, &vktest_dma_ops);

	vktest->vdpa.dma_dev = dev;

	mutex_init(&vktest->mutex);
	file->private_data = vktest;

	return ret;

err_put_device:
	put_device(dev);
	return ret;
}

static int vktest_release(struct inode *inode, struct file *file)
{
	struct vktest *vktest = file->private_data;
	struct vhost_dev *vhost = vktest->vhost;

	/* The device is not registered until a vhost is attached. */
	if (vhost)
		vdpa_unregister_device(&vktest->vdpa);
	else
		put_device(&vktest->vdpa.dev);

	return 0;
}

#define VKTEST_ATTACH_VHOST _IOW(0xbf, 0x31, int)

static int vktest_attach_vhost(struct vktest *vktest, int fd)
{
	struct vhost_dev *vhost;
	int ret;
	int i;

	if (vktest->vhost)
		return -EBUSY;

	for (i = 0; i < ARRAY_SIZE(vktest->vqs); i++) {
		struct vktest_vq *vq = &vktest->vqs[i];

		if (!vq->kick || !vq->call)
			return -EINVAL;
	}

	vhost = vhost_dev_get(fd);
	if (IS_ERR(vhost))
		return PTR_ERR(vhost);

	vktest->vhost = vhost;

	/* 1:1 mapping */
	ret = vhost_dev_iotlb_update(vhost, 0, ULLONG_MAX, 0, VHOST_ACCESS_RW);
	if (ret)
		goto put_vhost;

	ret = vdpa_register_device(&vktest->vdpa, ARRAY_SIZE(vktest->vqs));
	if (ret)
		goto put_vhost;

	return 0;

put_vhost:
	vhost_dev_put(vktest->vhost);
	vktest->vhost = NULL;
	return ret;
}

static int vktest_set_vring_kick(struct vktest *vktest,
				 const struct vhost_vring_file *vringf)
{
	unsigned int idx = vringf->index;
	struct eventfd_ctx *kick;

	if (idx >= sizeof(vktest->vqs))
		return -EINVAL;

	kick = eventfd_ctx_fdget(vringf->fd);
	if (IS_ERR(kick))
		return PTR_ERR(kick);

	vktest->vqs[idx].kick = kick;

	return 0;
}

static int vktest_call_wakeup(wait_queue_entry_t *wait, unsigned int mode,
			      int sync, void *key)
{
	struct vktest_vq *vq = container_of(wait, struct vktest_vq, call_wait);
	unsigned long flags = (unsigned long)key;

	if (flags & POLLIN)
		irq_work_queue(&vq->irq_work);

	return 0;
}

static void vktest_call_queue_proc(struct file *file, wait_queue_head_t *wqh,
				   poll_table *pt)
{
	struct vktest_vq *vq = container_of(pt, struct vktest_vq, call_pt);

	vq->wqh = wqh;
	add_wait_queue(wqh, &vq->call_wait);
}

static int vktest_set_vring_call(struct vktest *vktest,
				 const struct vhost_vring_file *vringf)
{
	unsigned int idx = vringf->index;
	struct fd eventfd;
	struct eventfd_ctx *call;
	struct vktest_vq *vq;
	__poll_t events;

	if (idx >= sizeof(vktest->vqs))
		return -EINVAL;

	eventfd = fdget(vringf->fd);
	if (!eventfd.file)
		return -EBADF;

	call = eventfd_ctx_fileget(eventfd.file);
	if (IS_ERR(call)) {
		fdput(eventfd);
		return PTR_ERR(call);
	}

	vq = &vktest->vqs[idx];
	vq->call = call;

	init_waitqueue_func_entry(&vq->call_wait, vktest_call_wakeup);
	init_poll_funcptr(&vq->call_pt, vktest_call_queue_proc);

	events = vfs_poll(eventfd.file, &vq->call_pt);
	if (events & POLLIN)
		vktest_call_notify(vq);

	return 0;
}

static long vktest_ioctl(struct file *file, unsigned int ioctl,
			 unsigned long arg)
{
	struct vktest *vktest = file->private_data;
	void __user *userp = (void __user *)arg;
	struct vhost_vring_file vringf;
	long ret = -ENOIOCTLCMD;

	mutex_lock(&vktest->mutex);

	switch (ioctl) {
	case VKTEST_ATTACH_VHOST:
		ret = vktest_attach_vhost(vktest, arg);
		break;
	case VHOST_SET_VRING_KICK:
		if (copy_from_user(&vringf, userp, sizeof(vringf))) {
			ret = -EFAULT;
			break;
		}
		ret = vktest_set_vring_kick(vktest, &vringf);
		break;
	case VHOST_SET_VRING_CALL:
		if (copy_from_user(&vringf, userp, sizeof(vringf))) {
			ret = -EFAULT;
			break;
		}
		ret = vktest_set_vring_call(vktest, &vringf);
		break;
	}

	mutex_unlock(&vktest->mutex);

	return ret;
}

static const struct file_operations vktest_fops = {
	.owner = THIS_MODULE,
	.release = vktest_release,
	.unlocked_ioctl = vktest_ioctl,
	.open = vktest_open,
	.llseek = noop_llseek,
};

static struct miscdevice vktest_misc = {
	MISC_DYNAMIC_MINOR,
	"vktest",
	&vktest_fops,
};

static int __init vktest_init(void)
{
	return misc_register(&vktest_misc);
}

static void __exit vktest_exit(void)
{
	misc_deregister(&vktest_misc);
}

module_init(vktest_init);
module_exit(vktest_exit);

MODULE_LICENSE("GPL v2");
