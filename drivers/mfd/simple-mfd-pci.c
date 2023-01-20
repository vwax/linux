// SPDX-License-Identifier: GPL-2.0-only

#include <linux/module.h>
#include <linux/of_platform.h>
#include <linux/pci.h>

static int simple_mfd_pci_probe(struct pci_dev *pdev,
				const struct pci_device_id *id)
{
	return devm_of_platform_populate(&pdev->dev);
}

static struct pci_driver simple_mfd_pci_driver = {
	/* No id_table, use new_id in sysfs */
	.name = "simple-mfd-pci",
	.probe = simple_mfd_pci_probe,
};

module_pci_driver(simple_mfd_pci_driver);

MODULE_LICENSE("GPL");
