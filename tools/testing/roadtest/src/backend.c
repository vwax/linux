// SPDX-License-Identifier: GPL-2.0-only
// Copyright Axis Communications AB

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <err.h>
#include <getopt.h>
#include <stdlib.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <sys/un.h>
#include <unistd.h>
#include <stdio.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <linux/virtio_gpio.h>
#include <linux/virtio_i2c.h>
#include <linux/virtio_pcidev.h>
#include <linux/kernel.h>
#include <linux/list.h>

#include "libvhost-user.h"

enum watch_type {
	LISTEN,
	SOCKET_WATCH,
	VU_WATCH,
};

struct watch {
	VuDev *dev;
	enum watch_type type;
	int fd;
	void *func;
	void *data;
	struct list_head list;
};

struct vhost_user_i2c {
	VuDev dev;
	FILE *control;
};

struct vhost_user_gpio {
	VuDev dev;
	FILE *control;
	VuVirtqElement *irq_elements[64];
};

struct vhost_user_pci {
	VuDev dev;
	FILE *control;
	bool bar_written;
};

#define dbg(...)                                                               \
	do {                                                                   \
		if (0) {                                                       \
			fprintf(stderr, __VA_ARGS__);                          \
		}                                                              \
	} while (0)

static LIST_HEAD(watches);

static int epfd;

static PyObject *py_i2c_read, *py_i2c_write, *py_process_control;
static PyObject *py_gpio_set_irq_type, *py_gpio_unmask;
static PyObject *py_platform_read, *py_platform_write;
static PyObject *py_gpio_set_value;

static const char *opt_main_script;
static char *opt_gpio_socket;
static char *opt_i2c_socket;
static char *opt_pci_socket;

static struct vhost_user_gpio gpio;
static struct vhost_user_i2c i2c;
static struct vhost_user_pci pci;

static void dump_iov(const char *what, struct iovec *iovec, unsigned int count)
{
	int i;

	dbg("dumping %s with count %u\n", what, count);

	for (i = 0; i < count; i++) {
		struct iovec *iov = &iovec[0];

		dbg("i %d base %p len %zu\n", i, iov->iov_base, iov->iov_len);
	}
}

static bool i2c_read(struct vhost_user_i2c *vi, uint16_t addr, void *data,
		     size_t len)
{
	PyObject *pArgs, *pValue;

	dbg("i2c read addr %#x len %zu\n", addr, len);

	pArgs = PyTuple_New(2);
	pValue = PyLong_FromLong(len);
	PyTuple_SetItem(pArgs, 0, PyLong_FromUnsignedLong(addr));
	PyTuple_SetItem(pArgs, 1, pValue);

	pValue = PyObject_CallObject(py_i2c_read, pArgs);
	Py_DECREF(pArgs);
	if (!pValue) {
		PyErr_Print();
		return false;
	}

	unsigned char *buffer;
	Py_ssize_t length;

	if (PyBytes_AsStringAndSize(pValue, (char **)&buffer, &length) < 0) {
		PyErr_Print();
		errx(1, "invalid result from i2c.read()");
	}
	if (length != len) {
		errx(1,
		     "unexpected length from i2c.read(), expected %zu, got %zu",
		     len, length);
	}

	memcpy(data, buffer, len);

	return true;
}

static bool i2c_write(struct vhost_user_i2c *vi, uint16_t addr,
		      const void *data, size_t len)
{
	PyObject *pArgs, *pValue;

	dbg("i2c write addr %#x len %zu\n", addr, len);

	pArgs = PyTuple_New(2);
	pValue = PyBytes_FromStringAndSize(data, len);
	PyTuple_SetItem(pArgs, 0, PyLong_FromUnsignedLong(addr));
	PyTuple_SetItem(pArgs, 1, pValue);

	pValue = PyObject_CallObject(py_i2c_write, pArgs);
	Py_DECREF(pArgs);
	if (!pValue) {
		PyErr_Print();
		return false;
	}

	return true;
}

static unsigned long platform_read(unsigned long addr, unsigned long size)
{
	PyObject *pArgs, *pAddr, *pSize, *pValue;

	dbg("platform read addr %#lx size %zu\n", addr, size);

	pArgs = PyTuple_New(2);

	pAddr = PyLong_FromUnsignedLong(addr);
	pSize = PyLong_FromUnsignedLong(size);

	PyTuple_SetItem(pArgs, 0, pAddr);
	PyTuple_SetItem(pArgs, 1, pSize);

	pValue = PyObject_CallObject(py_platform_read, pArgs);
	Py_DECREF(pArgs);
	if (!pValue) {
		PyErr_Print();
		errx(1, "platform.read() failed");
	}

	unsigned long value;
	value = PyLong_AsUnsignedLong(pValue);
	if (value == (unsigned long)-1 && PyErr_Occurred()) {
		PyErr_Print();
		errx(1, "invalid result from platform.read()");
	}

	return value;
}

static void platform_write(struct vhost_user_pci *pci, unsigned long addr,
						   unsigned long value, unsigned long size)
{
	PyObject *pArgs, *pAddr, *pSize, *pValue;

	dbg("platform write addr %#lx size %zu value %#lx\n", addr, size, value);

	pArgs = PyTuple_New(3);

	pAddr = PyLong_FromUnsignedLong(addr);
	pSize = PyLong_FromUnsignedLong(size);
	pValue = PyLong_FromUnsignedLong(value);

	PyTuple_SetItem(pArgs, 0, pAddr);
	PyTuple_SetItem(pArgs, 1, pSize);
	PyTuple_SetItem(pArgs, 2, pValue);

	pValue = PyObject_CallObject(py_platform_write, pArgs);
	Py_DECREF(pArgs);
	if (!pValue) {
		PyErr_Print();
		errx(1, "platform.write() failed");
	}
}

static void gpio_send_irq_response(struct vhost_user_gpio *gpio,
				   unsigned int pin, unsigned int status);

static PyObject *cbackend_trigger_gpio_irq(PyObject *self, PyObject *args)
{
	unsigned int pin;

	if (!PyArg_ParseTuple(args, "I", &pin))
		return NULL;

	dbg("trigger gpio %u irq\n", pin);

	gpio_send_irq_response(&gpio, pin, VIRTIO_GPIO_IRQ_STATUS_VALID);

	Py_RETURN_NONE;
}

static PyObject *cbackend_dma_read(PyObject *self, PyObject *args)
{
	unsigned long addr, len, outlen;
	void *virt;

	if (!PyArg_ParseTuple(args, "kk", &addr, &len))
		return NULL;

	outlen = len;
	virt = vu_gpa_to_va(&pci.dev, &outlen, addr);
	dbg("virt %p addr %#lx len %#lx outlen %#lx\n", virt, addr, len, outlen);
	if (!virt) {
		PyErr_SetString(PyExc_BufferError, "DMA read from invalid address");
		return NULL;
	}
	if (outlen != len) {
		PyErr_SetString(PyExc_BufferError, "DMA read overflows area");
		return NULL;
	}

	return PyBytes_FromStringAndSize(virt, len);
}

static PyObject *cbackend_dma_write(PyObject *self, PyObject *args)
{
	unsigned long addr, outlen;
	Py_buffer buffer;
	void *virt;

	if (!PyArg_ParseTuple(args, "ky*", &addr, &buffer))
		return NULL;

	outlen = buffer.len;
	virt = vu_gpa_to_va(&pci.dev, &outlen, addr);
	dbg("virt %p addr %#lx len %#lx outlen %#lx\n", virt, addr, buffer.len, outlen);
	if (!virt) {
		PyBuffer_Release(&buffer);
		PyErr_SetString(PyExc_BufferError, "DMA write to invalid address");
		return NULL;
	}
	if (outlen != buffer.len) {
		PyBuffer_Release(&buffer);
		PyErr_SetString(PyExc_BufferError, "DMA write overflows area");
		return NULL;
	}

	memcpy(virt, buffer.buf, buffer.len);
	PyBuffer_Release(&buffer);

	Py_RETURN_NONE;
}

static PyMethodDef EmbMethods[] = {
	{ "trigger_gpio_irq", cbackend_trigger_gpio_irq, METH_VARARGS,
	  "Return the number of arguments received by the process." },
	{ "dma_read", cbackend_dma_read, METH_VARARGS,
	  "DMA read." },
	{ "dma_write", cbackend_dma_write, METH_VARARGS,
	  "DMA write." },
	{ NULL, NULL, 0, NULL }
};

static PyModuleDef EmbModule = { PyModuleDef_HEAD_INIT,
				 "cbackend",
				 NULL,
				 -1,
				 EmbMethods,
				 NULL,
				 NULL,
				 NULL,
				 NULL };

static PyObject *PyInit_cbackend(void)
{
	return PyModule_Create(&EmbModule);
}

static void init_python_i2c(PyObject *backend)
{
	PyObject *i2c = PyObject_GetAttrString(backend, "i2c");

	if (!i2c) {
		PyErr_Print();
		errx(1, "Error getting backend.i2c");
	}

	py_i2c_read = PyObject_GetAttrString(i2c, "read");
	if (!py_i2c_read) {
		PyErr_Print();
		errx(1, "Error getting i2c.read");
	}

	py_i2c_write = PyObject_GetAttrString(i2c, "write");
	if (!py_i2c_write) {
		PyErr_Print();
		errx(1, "Error getting i2c.write");
	}
}

static void init_python_gpio(PyObject *backend)
{
	PyObject *gpio = PyObject_GetAttrString(backend, "gpio");

	if (!gpio) {
		PyErr_Print();
		errx(1, "error getting backend.gpio");
	}

	py_gpio_set_irq_type = PyObject_GetAttrString(gpio, "set_irq_type");
	if (!py_gpio_set_irq_type) {
		PyErr_Print();
		errx(1, "error getting gpio.set_irq_type");
	}

	py_gpio_set_value = PyObject_GetAttrString(gpio, "set_value");
	if (!py_gpio_set_value) {
		PyErr_Print();
		errx(1, "error getting gpio.set_value");
	}

	py_gpio_unmask = PyObject_GetAttrString(gpio, "unmask");
	if (!py_gpio_unmask) {
		PyErr_Print();
		errx(1, "error getting gpio.unmask");
	}
}

static void init_python_platform(PyObject *backend)
{
	PyObject *platform = PyObject_GetAttrString(backend, "platform");

	if (!platform) {
		PyErr_Print();
		errx(1, "Error getting backend.platform");
	}

	py_platform_read = PyObject_GetAttrString(platform, "read");
	if (!py_platform_read) {
		PyErr_Print();
		errx(1, "Error getting platform.read");
	}

	py_platform_write = PyObject_GetAttrString(platform, "write");
	if (!py_platform_write) {
		PyErr_Print();
		errx(1, "Error getting platform.write");
	}
}

static void init_python(void)
{
	PyObject *mainmod, *backend;
	FILE *file;

	PyImport_AppendInittab("cbackend", &PyInit_cbackend);

	Py_Initialize();

	file = fopen(opt_main_script, "r");
	if (!file)
		err(1, "open %s", opt_main_script);

	if (PyRun_SimpleFile(file, "main.py") < 0) {
		PyErr_Print();
		errx(1, "error running %s", opt_main_script);
	}
	fclose(file);

	mainmod = PyImport_AddModule("__main__");
	if (!mainmod) {
		PyErr_Print();
		errx(1, "error getting __main__");
	}

	backend = PyObject_GetAttrString(mainmod, "backend");
	if (!backend) {
		PyErr_Print();
		errx(1, "error getting backend");
	}

	py_process_control = PyObject_GetAttrString(backend, "process_control");
	if (!py_process_control) {
		PyErr_Print();
		errx(1, "error getting backend.process_control");
	}

	init_python_i2c(backend);
	init_python_platform(backend);
	init_python_gpio(backend);
}

static void i2c_handle_cmdq(VuDev *dev, int qidx)
{
	struct vhost_user_i2c *vi =
		container_of(dev, struct vhost_user_i2c, dev);
	VuVirtq *vq = vu_get_queue(dev, qidx);
	VuVirtqElement *elem;

	for (;;) {
		struct virtio_i2c_out_hdr *hdr;
		struct iovec *resultv;
		size_t used = 0;
		bool ok = true;

		elem = vu_queue_pop(dev, vq, sizeof(VuVirtqElement));
		if (!elem)
			break;

		dbg("elem %p index %u out_num %u in_num %u\n", elem,
		    elem->index, elem->out_num, elem->in_num);
		dump_iov("out", elem->out_sg, elem->out_num);
		dump_iov("in", elem->in_sg, elem->in_num);

		assert(elem->out_sg[0].iov_len == sizeof(*hdr));
		hdr = elem->out_sg[0].iov_base;

		if ((elem->out_num == 1 || elem->out_num == 2) && elem->in_num == 1) {
			struct iovec *data = NULL;
			size_t datalen = 0;

			if (elem->out_num == 2) {
				data = &elem->out_sg[1];
				datalen = data->iov_len;
			}

			ok = i2c_write(vi, hdr->addr, data ? data->iov_base : NULL,
				       datalen);
			resultv = &elem->in_sg[0];
		} else if (elem->out_num == 1 && elem->in_num == 2) {
			struct iovec *data = &elem->in_sg[0];

			ok = i2c_read(vi, hdr->addr, data->iov_base,
				      data->iov_len);
			resultv = &elem->in_sg[1];
			used += data->iov_len;
		} else {
			assert(false);
		}

		struct virtio_i2c_in_hdr *inhdr = resultv->iov_base;

		inhdr->status = ok ? VIRTIO_I2C_MSG_OK : VIRTIO_I2C_MSG_ERR;

		used += sizeof(*inhdr);
		vu_queue_push(dev, vq, elem, used);
		free(elem);
	}

	vu_queue_notify(&vi->dev, vq);
}

static void i2c_queue_set_started(VuDev *dev, int qidx, bool started)
{
	VuVirtq *vq = vu_get_queue(dev, qidx);

	dbg("queue started %d:%d\n", qidx, started);

	vu_set_queue_handler(dev, vq, started ? i2c_handle_cmdq : NULL);
}

static bool i2cquit;
static bool gpioquit;
static bool pciquit;

static void remove_watch(VuDev *dev, int fd);

static int i2c_process_msg(VuDev *dev, VhostUserMsg *vmsg, int *do_reply)
{
	if (vmsg->request == VHOST_USER_NONE) {
		dbg("i2c disconnect");
		remove_watch(dev, -1);
		i2cquit = true;
		return true;
	}
	return false;
}
static int gpio_process_msg(VuDev *dev, VhostUserMsg *vmsg, int *do_reply)
{
	if (vmsg->request == VHOST_USER_NONE) {
		dbg("gpio disconnect");
		remove_watch(dev, -1);
		gpioquit = true;
		return true;
	}
	return false;
}

static int pci_process_msg(VuDev *dev, VhostUserMsg *vmsg, int *do_reply)
{
	if (vmsg->request == VHOST_USER_NONE) {
		dbg("pci disconnect");
		remove_watch(dev, -1);
		pciquit = true;
		return true;
	}
	return false;
}

static uint64_t i2c_get_features(VuDev *dev)
{
	return 1ull << VIRTIO_I2C_F_ZERO_LENGTH_REQUEST;
}

static const VuDevIface i2c_iface = {
	.get_features = i2c_get_features,
	.queue_set_started = i2c_queue_set_started,
	.process_msg = i2c_process_msg,
};

static void gpio_send_irq_response(struct vhost_user_gpio *gpio,
				   unsigned int pin, unsigned int status)
{
	assert(pin < ARRAY_SIZE(gpio->irq_elements));

	VuVirtqElement *elem = gpio->irq_elements[pin];
	VuVirtq *vq = vu_get_queue(&gpio->dev, 1);

	if (!elem) {
		dbg("no irq buf for pin %d\n", pin);
		assert(status != VIRTIO_GPIO_IRQ_STATUS_VALID);
		return;
	}

	struct virtio_gpio_irq_response *resp;

	assert(elem->out_num == 1);
	assert(elem->in_sg[0].iov_len == sizeof(*resp));

	resp = elem->in_sg[0].iov_base;
	resp->status = status;

	vu_queue_push(&gpio->dev, vq, elem, sizeof(*resp));
	gpio->irq_elements[pin] = NULL;
	free(elem);

	vu_queue_notify(&gpio->dev, vq);
}

static void gpio_set_irq_type(struct vhost_user_gpio *gpio, unsigned int pin,
			      unsigned int type)
{
	PyObject *pArgs, *pValue;

	pArgs = PyTuple_New(2);
	pValue = PyLong_FromLong(pin);
	PyTuple_SetItem(pArgs, 0, pValue);

	pValue = PyLong_FromLong(type);
	PyTuple_SetItem(pArgs, 1, pValue);

	pValue = PyObject_CallObject(py_gpio_set_irq_type, pArgs);
	if (!pValue) {
		PyErr_Print();
		errx(1, "error from gpio.set_irq_type()");
	}
	Py_DECREF(pArgs);

	if (type == VIRTIO_GPIO_IRQ_TYPE_NONE) {
		gpio_send_irq_response(gpio, pin,
				       VIRTIO_GPIO_IRQ_STATUS_INVALID);
	}
}

static void gpio_set_value(struct vhost_user_gpio *gpio, unsigned int pin,
                           unsigned int value)
{
	PyObject *pArgs, *pValue;

	pArgs = PyTuple_New(2);
	pValue = PyLong_FromLong(pin);
	PyTuple_SetItem(pArgs, 0, pValue);

	pValue = PyLong_FromLong(value);
	PyTuple_SetItem(pArgs, 1, pValue);

	pValue = PyObject_CallObject(py_gpio_set_value, pArgs);
	if (!pValue) {
		PyErr_Print();
		errx(1, "error from gpio.set_value()");
	}
	Py_DECREF(pArgs);
}

static void gpio_unmask(struct vhost_user_gpio *vi, unsigned int gpio)
{
	PyObject *pArgs, *pValue;

	pArgs = PyTuple_New(1);
	pValue = PyLong_FromLong(gpio);
	PyTuple_SetItem(pArgs, 0, pValue);

	pValue = PyObject_CallObject(py_gpio_unmask, pArgs);
	if (!pValue) {
		PyErr_Print();
		errx(1, "error from gpio.unmask()");
	}
	Py_DECREF(pArgs);
}

static void gpio_handle_cmdq(VuDev *dev, int qidx)
{
	struct vhost_user_gpio *vi =
		container_of(dev, struct vhost_user_gpio, dev);
	VuVirtq *vq = vu_get_queue(dev, qidx);
	VuVirtqElement *elem;

	while (1) {
		struct virtio_gpio_request *req;
		struct virtio_gpio_response *resp;

		elem = vu_queue_pop(dev, vq, sizeof(VuVirtqElement));
		if (!elem)
			break;

		dbg("elem %p index %u out_num %u in_num %u\n", elem,
		    elem->index, elem->out_num, elem->in_num);

		dump_iov("out", elem->out_sg, elem->out_num);
		dump_iov("in", elem->in_sg, elem->in_num);

		assert(elem->out_num == 1);
		assert(elem->in_num == 1);

		assert(elem->out_sg[0].iov_len == sizeof(*req));
		assert(elem->in_sg[0].iov_len == sizeof(*resp));

		req = elem->out_sg[0].iov_base;
		resp = elem->in_sg[0].iov_base;

		dbg("req type %#x gpio %#x value %#x\n", req->type, req->gpio,
		    req->value);

		switch (req->type) {
		case VIRTIO_GPIO_MSG_IRQ_TYPE:
			gpio_set_irq_type(vi, req->gpio, req->value);
			resp->value = 0;
			break;
		case VIRTIO_GPIO_MSG_GET_DIRECTION:
			dbg("get direction\n");
			resp->value = VIRTIO_GPIO_DIRECTION_IN;
			break;
		case VIRTIO_GPIO_MSG_SET_VALUE:
			dbg("set value\n");
			gpio_set_value(vi, req->gpio, req->value);
			break;
		default:
			resp->value = 0;
			/*
			 * The other types couldhooked up to Python later for
			 * testing of drivers' control of GPIOs.
			 */
			break;
		}

		resp->status = VIRTIO_GPIO_STATUS_OK;

		vu_queue_push(dev, vq, elem, sizeof(*resp));
		free(elem);
	}

	vu_queue_notify(&vi->dev, vq);
}

static void gpio_handle_eventq(VuDev *dev, int qidx)
{
	struct vhost_user_gpio *vi =
		container_of(dev, struct vhost_user_gpio, dev);
	VuVirtq *vq = vu_get_queue(dev, qidx);
	VuVirtqElement *elem;

	for (;;) {
		struct virtio_gpio_irq_request *req;
		struct virtio_gpio_irq_response *resp;

		elem = vu_queue_pop(dev, vq, sizeof(VuVirtqElement));
		if (!elem)
			break;

		dbg("elem %p index %u out_num %u in_num %u\n", elem,
		    elem->index, elem->out_num, elem->in_num);

		dump_iov("out", elem->out_sg, elem->out_num);
		dump_iov("in", elem->in_sg, elem->in_num);

		assert(elem->out_num == 1);
		assert(elem->in_num == 1);

		assert(elem->out_sg[0].iov_len == sizeof(*req));
		assert(elem->in_sg[0].iov_len == sizeof(*resp));

		req = elem->out_sg[0].iov_base;
		resp = elem->in_sg[0].iov_base;

		dbg("irq req gpio %#x\n", req->gpio);

		assert(req->gpio < ARRAY_SIZE(vi->irq_elements));
		assert(vi->irq_elements[req->gpio] == NULL);

		vi->irq_elements[req->gpio] = elem;

		gpio_unmask(vi, req->gpio);
	}
}

static void gpio_queue_set_started(VuDev *dev, int qidx, bool started)
{
	VuVirtq *vq = vu_get_queue(dev, qidx);

	dbg("%s %d:%d\n", __func__, qidx, started);

	if (qidx == 0)
		vu_set_queue_handler(dev, vq,
				     started ? gpio_handle_cmdq : NULL);
	if (qidx == 1)
		vu_set_queue_handler(dev, vq,
				     started ? gpio_handle_eventq : NULL);
}

static int gpio_get_config(VuDev *dev, uint8_t *config, uint32_t len)
{
	struct vhost_user_gpio *gpio =
		container_of(dev, struct vhost_user_gpio, dev);
	static struct virtio_gpio_config gpioconfig = {
		.ngpio = ARRAY_SIZE(gpio->irq_elements),
	};

	dbg("%s: len %u\n", __func__, len);

	if (len > sizeof(struct virtio_gpio_config))
		return -1;

	memcpy(config, &gpioconfig, len);

	return 0;
}

static uint64_t gpio_get_protocol_features(VuDev *dev)
{
	return 1ull << VHOST_USER_PROTOCOL_F_CONFIG;
}

static uint64_t gpio_get_features(VuDev *dev)
{
	return 1ull << VIRTIO_GPIO_F_IRQ;
}

static const VuDevIface gpio_vuiface = {
	.get_features = gpio_get_features,
	.queue_set_started = gpio_queue_set_started,
	.process_msg = gpio_process_msg,
	.get_config = gpio_get_config,
	.get_protocol_features = gpio_get_protocol_features,
};

static void pci_handle_cmd(VuDev *dev, int qidx)
{
        struct vhost_user_pci *vi =
                container_of(dev, struct vhost_user_pci, dev);
        VuVirtq *vq = vu_get_queue(dev, qidx);
        VuVirtqElement *elem;

        dbg("%s\n", __func__);

        for (;;) {
                struct virtio_pcidev_msg *hdr;
                // struct iovec *result;
                size_t used = 0;
                // bool ok = true;

                elem = vu_queue_pop(dev, vq, sizeof(VuVirtqElement));
                if (!elem) {
                        break;
                }

                dbg("elem %p index %u out_num %u in_num %u\n", elem,
                       elem->index, elem->out_num, elem->in_num);
                dump_iov("out", elem->out_sg, elem->out_num);
                dump_iov("in", elem->in_sg, elem->in_num);

                assert(elem->out_sg[0].iov_len >= sizeof(*hdr));
                hdr = elem->out_sg[0].iov_base;

                dbg("PCI op %#x size %#x addr %#llx\n", hdr->op, hdr->size,
                       hdr->addr);

                switch (hdr->op) {
				case VIRTIO_PCIDEV_OP_MMIO_READ: {
					assert(elem->in_num == 1 && elem->out_num == 1);
					assert(hdr->size == 4);

					struct iovec *resultv = &elem->in_sg[0];
					assert(resultv->iov_len >= 4);

					unsigned int value = platform_read(hdr->addr, hdr->size);

					memcpy(resultv->iov_base, &value, 4);
					used += hdr->size;
					break;
				}
				case VIRTIO_PCIDEV_OP_MMIO_WRITE: {
					unsigned int value;

					assert(elem->in_num == 0);
					assert(elem->out_num == 1 || elem->out_num == 2);
					assert(hdr->size == 4);

					if (elem->out_num == 1) {
						// Posted
						struct iovec *datav = &elem->out_sg[0];
						assert(datav->iov_len >= sizeof(*hdr) + hdr->size);
						value = *(unsigned int *) (datav->iov_base + sizeof(*hdr));
					}	else {
						// Non-posted
						struct iovec *datav = &elem->out_sg[1];
						assert(datav->iov_len >= 4);
						value = *(unsigned int *) (datav->iov_base);
					}

					platform_write(vi, hdr->addr, value, hdr->size);
					break;
				}
				default:
					assert(false);
					break;
                }

                used += sizeof(*hdr);
                vu_queue_push(dev, vq, elem, used);
                free(elem);
        }

        vu_queue_notify(&vi->dev, vq);
}

static void pci_queue_set_started(VuDev *dev, int qidx, bool started)
{
        VuVirtq *vq = vu_get_queue(dev, qidx);

        dbg("queue started %d:%d\n", qidx, started);

        if (qidx == 0) {
                vu_set_queue_handler(dev, vq, started ? pci_handle_cmd : NULL);
        }
}

static const VuDevIface pci_iface = {
	.queue_set_started = pci_queue_set_started,
	.process_msg = pci_process_msg,
};

static void panic(VuDev *dev, const char *err)
{
	fprintf(stderr, "panicking: %s!", err);
	abort();
}

static struct watch *new_watch(struct VuDev *dev, int fd, enum watch_type type,
			       void *func, void *data)
{
	struct watch *watch = malloc(sizeof(*watch));

	assert(watch);

	watch->dev = dev;
	watch->fd = fd;
	watch->func = func;
	watch->data = data;
	watch->type = type;

	list_add(&watch->list, &watches);

	return watch;
}

static void set_watch(VuDev *dev, int fd, int condition, vu_watch_cb cb,
		      void *data)
{
	struct watch *watch = new_watch(dev, fd, VU_WATCH, cb, data);
	int ret;

	struct epoll_event ev = {
		.events = EPOLLIN,
		.data.ptr = watch,
	};

	dbg("set watch epfd %d fd %d condition %d cb %p\n", epfd, fd, condition,
	    cb);

	epoll_ctl(epfd, EPOLL_CTL_DEL, fd, NULL);

	ret = epoll_ctl(epfd, EPOLL_CTL_ADD, fd, &ev);
	if (ret < 0)
		err(1, "epoll_ctl");
}

static void remove_watch(VuDev *dev, int fd)
{
	struct watch *watch, *tmp;

	list_for_each_entry_safe(watch, tmp, &watches, list) {
		if (watch->dev != dev)
			continue;
		if (fd >= 0 && watch->fd != fd)
			continue;

		epoll_ctl(epfd, EPOLL_CTL_DEL, watch->fd, NULL);

		list_del(&watch->list);
		free(watch);
	}
}

static int unix_listen(const char *path)
{
	struct sockaddr_un un = {
		.sun_family = AF_UNIX,
	};
	int sock;
	int ret;

	unlink(path);

	sock = socket(PF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
	if (sock < 0)
		err(1, "socket");

	if (sizeof(un.sun_path) <= strlen(path))
		errx(1, "socket path too long: %s", path);

	strcpy(un.sun_path, path);

	ret = bind(sock, (struct sockaddr *)&un, sizeof(un));
	if (ret < 0)
		err(1, "bind");

	ret = listen(sock, 1);
	if (ret < 0)
		err(1, "listen");

	return sock;
}

static void dev_add_watch(int epfd, struct watch *watch)
{
	struct epoll_event event = {
		.events = EPOLLIN | EPOLLONESHOT,
		.data.ptr = watch,
	};
	int ret;

	ret = epoll_ctl(epfd, EPOLL_CTL_ADD, watch->fd, &event);
	if (ret < 0)
		err(1, "EPOLL_CTL_ADD");
}

static VuDev *gpio_init(int epfd, const char *path)
{
	struct watch *watch;
	VuDev *dev;
	int lsock;
	bool rc;

	lsock = unix_listen(path);
	if (lsock < 0)
		err(1, "listen %s", path);

	rc = vu_init(&gpio.dev, 2, lsock, panic, NULL, set_watch,
		     remove_watch, &gpio_vuiface);
	assert(rc == true);

	dev = &gpio.dev;
	watch = new_watch(dev, lsock, LISTEN, vu_dispatch, dev);

	dev_add_watch(epfd, watch);

	return dev;
}

static VuDev *i2c_init(int epfd, const char *path)
{
	VuDev *dev = &i2c.dev;
	struct watch *watch;
	int lsock;
	bool rc;

	lsock = unix_listen(path);
	if (lsock < 0)
		err(1, "listen %s", path);

	rc = vu_init(dev, 1, lsock, panic, NULL, set_watch,
		     remove_watch, &i2c_iface);
	assert(rc == true);

	watch = new_watch(dev, lsock, LISTEN, vu_dispatch, dev);

	dev_add_watch(epfd, watch);

	return dev;
}

static VuDev *pci_init(int epfd, const char *path)
{
	VuDev *dev = &pci.dev;
	struct watch *watch;
	int lsock;
	bool rc;

	lsock = unix_listen(path);
	if (lsock < 0)
		err(1, "listen %s", path);

	rc = vu_init(dev, 2, lsock, panic, NULL, set_watch,
		     remove_watch, &pci_iface);
	assert(rc == true);

	watch = new_watch(dev, lsock, LISTEN, vu_dispatch, dev);

	dev_add_watch(epfd, watch);

	return dev;
}

static pid_t run_uml(char **argv)
{
	int log, null, ret;
	pid_t pid;

	pid = fork();
	if (pid < 0)
		err(1, "fork");
	if (pid > 0)
		return pid;

	chdir(getenv("ROADTEST_WORK_DIR"));

	log = open("uml.txt", O_WRONLY | O_TRUNC | O_APPEND | O_CREAT, 0600);
	if (log < 0)
		err(1, "open uml.txt");

	null = open("/dev/null", O_RDONLY);
	if (null < 0)
		err(1, "open null");

	ret = dup2(null, 0);
	if (ret < 0)
		err(1, "dup2");

	ret = dup2(log, 1);
	if (ret < 0)
		err(1, "dup2");

	ret = dup2(log, 2);
	if (ret < 0)
		err(1, "dup2");

	execvpe(argv[0], argv, environ);
	err(1, "execve");

	return -1;
}

int main(int argc, char *argv[])
{
	static struct option long_option[] = {
		{ "main-script", required_argument, 0, 'm' },
		{ "gpio-socket", required_argument, 0, 'g' },
		{ "i2c-socket", required_argument, 0, 'i' },
		{ "pci-socket", required_argument, 0, 'p' },
	};

	while (1) {
		int c = getopt_long(argc, argv, "", long_option, NULL);

		if (c == -1)
			break;

		switch (c) {
		case 'm':
			opt_main_script = optarg;
			break;

		case 'g':
			opt_gpio_socket = optarg;
			break;

		case 'i':
			opt_i2c_socket = optarg;
			break;

		case 'p':
			opt_pci_socket = optarg;
			break;

		default:
			errx(1, "getopt");
		}
	}

	if (!opt_main_script || !opt_gpio_socket || !opt_i2c_socket)
		errx(1, "Invalid arguments");

	epfd = epoll_create1(EPOLL_CLOEXEC);
	if (epfd < 0)
		err(1, "epoll_create1");

	init_python();

	gpio_init(epfd, opt_gpio_socket);
	i2c_init(epfd, opt_i2c_socket);
	pci_init(epfd, opt_pci_socket);

	run_uml(&argv[optind]);

	while (1) {
		struct epoll_event events[10];
		int nfds;
		int i;

		nfds = epoll_wait(epfd, events, ARRAY_SIZE(events), -1);
		if (nfds < 0) {
			if (errno == EINTR) {
				continue;

				err(1, "epoll_wait");
			}
		}

		if (!PyObject_CallObject(py_process_control, NULL)) {
			PyErr_Print();
			errx(1, "error from backend.process_control");
		}

		for (i = 0; i < nfds; i++) {
			struct epoll_event *event = &events[i];
			struct watch *watch = event->data.ptr;
			int fd;

			switch (watch->type) {
			case LISTEN:
				fd = accept(watch->fd, NULL, NULL);
				close(watch->fd);
				if (fd == -1)
					err(1, "accept");

				watch->dev->sock = fd;
				watch->fd = fd;
				watch->type = SOCKET_WATCH;

				struct epoll_event event = {
					.events = EPOLLIN,
					.data.ptr = watch,
				};

				int ret = epoll_ctl(epfd, EPOLL_CTL_ADD, fd,
						    &event);
				if (ret < 0)
					err(1, "epoll_ctl");

				break;
			case SOCKET_WATCH:
				vu_dispatch(watch->dev);
				break;
			case VU_WATCH:
				((vu_watch_cb)(watch->func))(watch->dev, POLLIN,
							     watch->data);
				break;
			default:
				fprintf(stderr, "abort!");
				abort();
			}
		}

		if (i2cquit && gpioquit && pciquit)
			break;
	}

	vu_deinit(&i2c.dev);
	vu_deinit(&gpio.dev);
	vu_deinit(&pci.dev);

	Py_Finalize();

	return 0;
}
