/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_DEVICETREE_H
#define BRICKWRIGHT_ZEPHYR_DEVICETREE_H
/* The external CC2564C is described directly by the NuttX board port. */
#define DT_HAS_CHOSEN(node) 1
#define DT_CHOSEN(node) node
#define DEVICE_DT_GET(node) (&brickwright_hci_device)
#define DT_NODE_HAS_PROP(node, property) 0
#define DT_PROP_OR(node, property, fallback) fallback
#define DT_ENUM_IDX_OR(node, property, fallback) fallback
#endif
