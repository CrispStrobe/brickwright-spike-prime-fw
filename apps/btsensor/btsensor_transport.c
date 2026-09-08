/* SPDX-License-Identifier: Apache-2.0 */

#include <nuttx/config.h>

#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <brickwright/hci_driver.h>
#include <brickwright/hub_transport.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/classic/classic.h>
#include <zephyr/settings/settings.h>

#include "btsensor_transport.h"

static bool g_started;
static bool g_le_advertising;

static const struct bt_le_adv_param *const g_le_params =
  BT_LE_ADV_PARAM(BT_LE_ADV_OPT_CONN | BT_LE_ADV_OPT_USE_IDENTITY,
                  BT_GAP_ADV_FAST_INT_MIN_2, BT_GAP_ADV_FAST_INT_MAX_2,
                  NULL);

int btsensor_transport_start(btsensor_transport_receive_cb receive,
                             btsensor_transport_state_cb state,
                             void *context)
{
  int ret;

  if (g_started)
    {
      return -EALREADY;
    }

#ifdef CONFIG_APP_BTSENSOR_VIRTUAL_CONTROLLER
  static const uint8_t virtual_address[6] = {
    0x06, 0x05, 0x04, 0x03, 0x02, 0x01
  };
  ret = brickwright_hci_configure(BRICKWRIGHT_HCI_BACKEND_VIRTUAL,
                                  NULL, virtual_address);
#else
  ret = brickwright_hci_configure(BRICKWRIGHT_HCI_BACKEND_PHYSICAL,
                                  "/dev/ttyBT", NULL);
#endif
  if (ret < 0)
    {
      return ret;
    }

  ret = bt_enable(NULL);
  if (ret < 0)
    {
      return ret;
    }

  ret = settings_load();
  if (ret < 0)
    {
      (void)bt_disable();
      return ret;
    }

  ret = brickwright_hub_transport_register(receive, state, context);
  if (ret < 0)
    {
      (void)bt_disable();
      return ret;
    }

  g_started = true;
  g_le_advertising = false;
  return 0;
}

int btsensor_transport_set_visible(bool visible)
{
  int ret;

  if (!g_started)
    {
      return -ENODEV;
    }

  if (visible)
    {
      ret = bt_br_set_connectable(true, NULL);
      if (ret < 0 && ret != -EALREADY)
        {
          return ret;
        }

      ret = bt_br_set_discoverable(true, false);
      if (ret < 0 && ret != -EALREADY)
        {
          (void)bt_br_set_connectable(false, NULL);
          return ret;
        }

      if (!g_le_advertising)
        {
          ret = bt_le_adv_start(g_le_params, NULL, 0, NULL, 0);
          if (ret < 0)
            {
              (void)bt_br_set_discoverable(false, false);
              (void)bt_br_set_connectable(false, NULL);
              return ret;
            }

          g_le_advertising = true;
        }

      return 0;
    }

  if (g_le_advertising)
    {
      ret = bt_le_adv_stop();
      if (ret < 0)
        {
          return ret;
        }

      g_le_advertising = false;
    }

  ret = bt_br_set_discoverable(false, false);
  if (ret < 0 && ret != -EALREADY)
    {
      return ret;
    }

  ret = bt_br_set_connectable(false, NULL);
  return ret == -EALREADY ? 0 : ret;
}

bool btsensor_transport_connected(enum brickwright_hub_link link)
{
  return g_started && brickwright_hub_transport_connected(link);
}

int btsensor_transport_send(enum brickwright_hub_link link,
                            const void *data, size_t length)
{
  return g_started ? brickwright_hub_transport_send(link, data, length) :
                     -ENODEV;
}

int btsensor_transport_stop(void)
{
  int ret;

  if (!g_started)
    {
      return -EALREADY;
    }

  (void)btsensor_transport_set_visible(false);
  brickwright_hub_transport_unregister();
  ret = bt_disable();
  if (ret == 0)
    {
      g_started = false;
      g_le_advertising = false;
    }

  return ret;
}
