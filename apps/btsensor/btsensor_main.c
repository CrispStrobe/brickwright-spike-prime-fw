/* SPDX-License-Identifier: Apache-2.0 */

#include <nuttx/config.h>

#include <errno.h>
#include <stdbool.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "btsensor_cmd.h"
#include "btsensor_classic.h"
#include "btsensor_lifecycle.h"
#include "btsensor_modern.h"
#include "btsensor_modern_backend.h"
#ifdef CONFIG_APP_BTSENSOR_NUTTX_PERIPHERALS
#  include "btsensor_nuttx_peripheral.h"
#endif
#include "btsensor_modern_notify.h"
#include "btsensor_scheduler.h"
#include "btsensor_sound.h"
#include "btsensor_ti_payload.h"
#include "btsensor_transport.h"
#include "btsensor_tx.h"
#include "hub_protocol.h"
#include "spike_codec.h"

#ifndef CONFIG_APP_BTSENSOR_STOP_TIMEOUT_MS
#  define CONFIG_APP_BTSENSOR_STOP_TIMEOUT_MS 3000
#endif

static struct brickwright_hub_protocol g_modern_protocol;
static struct btsensor_modern g_modern_service;
static struct btsensor_modern_notifier g_modern_notifier;
static struct btsensor_timer_s g_modern_timer;
static struct btsensor_timer_s g_classic_timer;
static pthread_mutex_t g_modern_send_lock = PTHREAD_MUTEX_INITIALIZER;
static uint8_t g_modern_send_frame[BTSENSOR_TX_FRAME_MAX_SIZE];

int btsensor_hub_operation(const struct btsensor_modern_operation *operation)
{
  return btsensor_modern_backend_operation(operation);
}

#ifndef CONFIG_APP_BTSENSOR_NUTTX_PERIPHERALS
int btsensor_hub_snapshot(struct btsensor_modern_snapshot *snapshot)
{
  (void)snapshot;
  return -ENODATA;
}
#endif

static int modern_snapshot(struct btsensor_modern_snapshot *snapshot,
                           void *context)
{
  (void)context;
  return btsensor_hub_snapshot(snapshot);
}

static void modern_timer_tick(void *context)
{
  btsensor_modern_notifier_tick(context);
}

static int modern_timer_start(uint32_t period_ms, void *context)
{
  return btsensor_scheduler_timer_start(&g_modern_timer, period_ms,
                                         modern_timer_tick, context);
}

static void modern_timer_stop(void *context)
{
  (void)context;
  btsensor_scheduler_timer_stop(&g_modern_timer);
}

static uint64_t classic_now(void *context)
{
  struct timespec value;
  (void)context;
  clock_gettime(CLOCK_MONOTONIC, &value);
  return (uint64_t)value.tv_sec * 1000u + (uint64_t)value.tv_nsec / 1000000u;
}

static void classic_timer_tick(void *context)
{
  (void)context;
  btsensor_classic_timer_fired();
}

static int classic_timer_start(uint32_t delay_ms, void *context)
{
  (void)context;
  return btsensor_scheduler_timer_start_once(&g_classic_timer, delay_ms,
                                              classic_timer_tick, NULL);
}

static void classic_timer_stop(void *context)
{
  (void)context;
  btsensor_scheduler_timer_stop(&g_classic_timer);
}

static int modern_send(const uint8_t *message, size_t length,
                       bool high_priority, void *context)
{
  size_t frame_length;
  (void)context;
  pthread_mutex_lock(&g_modern_send_lock);
  int rc = bw_spike_pack(message, length, high_priority, g_modern_send_frame,
                         sizeof(g_modern_send_frame), &frame_length);
  if (rc == BW_CODEC_OK)
    rc = btsensor_tx_try_enqueue_frame(g_modern_send_frame, frame_length);
  else
    rc = -EMSGSIZE;
  pthread_mutex_unlock(&g_modern_send_lock);
  return rc;
}

static int modern_operation(const struct btsensor_modern_operation *operation,
                            void *context)
{
  (void)context;
  if (operation && (operation->kind == BTSENSOR_MODERN_OP_SOUND_BEEP ||
                    operation->kind == BTSENSOR_MODERN_OP_SOUND_STOP))
    return btsensor_sound_operation(BRICKWRIGHT_HUB_LINK_BLE, operation);
  return btsensor_hub_operation(operation);
}

static int classic_operation(enum brickwright_hub_link link,
                             const struct btsensor_modern_operation *operation,
                             void *context)
{
  (void)context;
  if (operation && (operation->kind == BTSENSOR_MODERN_OP_SOUND_BEEP ||
                    operation->kind == BTSENSOR_MODERN_OP_SOUND_STOP))
    return btsensor_sound_operation(link, operation);
  return btsensor_modern_backend_operation_for_link(link, operation);
}

static int classic_tagged_operation(
    enum brickwright_hub_link link,
    const struct btsensor_modern_operation *operation,
    uint32_t *ownership_token, void *context)
{
  (void)context;
  return btsensor_modern_backend_operation_for_link_tagged(
      link, operation, ownership_token);
}

static int classic_end_owned(enum brickwright_hub_link link, uint8_t port,
                             uint32_t ownership_token, uint8_t end_state,
                             void *context)
{
  (void)context;
  return btsensor_modern_backend_end_motor_if_owned(
      link, port, ownership_token, end_state);
}

static int classic_snapshot(struct btsensor_modern_snapshot *snapshot,
                            void *context)
{
  (void)context;
  return btsensor_hub_snapshot(snapshot);
}

static int classic_send(enum brickwright_hub_link link, const uint8_t *data,
                        size_t length, void *context)
{
  (void)context;
  btsensor_tx_set_link(link, true);
  return btsensor_tx_try_enqueue_frame(data, length);
}

static int modern_interval(uint16_t interval_ms, void *context)
{
  return btsensor_modern_notifier_set_interval(interval_ms, context);
}

static int protocol_message(enum brickwright_protocol_kind kind,
                            const uint8_t *data, size_t length,
                            bool high_priority, void *context)
{
  (void)context;
  if (kind != BRICKWRIGHT_PROTOCOL_BLE_MESSAGE)
    {
      return -EPROTO;
    }

  return btsensor_modern_receive(&g_modern_service, data, length,
                                  high_priority);
}

static void transport_receive(enum brickwright_hub_link link,
                              const uint8_t *data, size_t length,
                              void *context)
{
  (void)context;
  btsensor_tx_set_link(link, true);
  if (link == BRICKWRIGHT_HUB_LINK_CLASSIC)
    {
      btsensor_cmd_feed_link(link, data, length);
      return;
    }

  if (link == BRICKWRIGHT_HUB_LINK_BLE)
    {
      (void)brickwright_hub_protocol_feed_ble(&g_modern_protocol,
                                               data, length);
    }
}

static void transport_state(enum brickwright_hub_link link, bool connected,
                            uint32_t generation, void *context)
{
  (void)context;
  if (link == BRICKWRIGHT_HUB_LINK_BLE && !connected)
    btsensor_modern_notifier_reset(&g_modern_notifier);
  btsensor_classic_link_state(link, connected);
  btsensor_sound_link_state(link, connected);
  btsensor_modern_backend_link_state(link, connected, generation);
}

static int services_start(void *context)
{
  static const struct btsensor_modern_config modern_config =
    {
      .rpc_major = 1,
      .rpc_minor = 0,
      .rpc_build = 0,
      .firmware_major = 0,
      .firmware_minor = 1,
      .firmware_build = 0,
      .product_group_device = 0,
    };
  (void)context;
#ifndef CONFIG_APP_BTSENSOR_VIRTUAL_CONTROLLER
  size_t service_pack_size;
  if (btsensor_ti_payload(&service_pack_size) == NULL ||
      service_pack_size == 0)
    return -ENOENT;
#endif
  int rc = btsensor_scheduler_acquire();
  if (rc < 0) return rc;
  memset(&g_modern_timer, 0, sizeof(g_modern_timer));
  memset(&g_classic_timer, 0, sizeof(g_classic_timer));
  btsensor_modern_init(&g_modern_service, &modern_config, modern_send,
                        modern_operation, modern_interval,
                        &g_modern_notifier);
  btsensor_modern_notifier_init(&g_modern_notifier, &g_modern_service,
                                 modern_snapshot, modern_timer_start,
                                 modern_timer_stop, &g_modern_notifier);
  brickwright_hub_protocol_init(&g_modern_protocol, protocol_message, NULL);
  btsensor_cmd_init();
  const struct btsensor_classic_config classic_config =
    {
      .operation = classic_operation,
      .tagged_operation = classic_tagged_operation,
      .end_owned = classic_end_owned,
      .snapshot = classic_snapshot,
      .send = classic_send,
      .now = classic_now,
      .timer_start = classic_timer_start,
      .timer_stop = classic_timer_stop,
      .context = NULL,
    };
  btsensor_classic_init(&classic_config);
  rc = btsensor_tx_init();
  if (rc < 0)
    {
      btsensor_modern_notifier_deinit(&g_modern_notifier);
      btsensor_scheduler_release();
      return rc;
    }

#ifdef CONFIG_APP_BTSENSOR_NUTTX_PERIPHERALS
  rc = btsensor_nuttx_peripheral_start();
  if (rc < 0)
    {
      btsensor_tx_deinit();
      btsensor_modern_notifier_deinit(&g_modern_notifier);
      btsensor_scheduler_release();
      return rc;
    }
#endif
  return 0;
}

static void services_stop(void *context)
{
  (void)context;
  btsensor_classic_link_state(BRICKWRIGHT_HUB_LINK_CLASSIC, false);
  btsensor_modern_notifier_deinit(&g_modern_notifier);
  btsensor_sound_shutdown();
  btsensor_modern_backend_shutdown();
  btsensor_tx_set_link(BRICKWRIGHT_HUB_LINK_CLASSIC, false);
  btsensor_tx_set_link(BRICKWRIGHT_HUB_LINK_BLE, false);
#ifdef CONFIG_APP_BTSENSOR_NUTTX_PERIPHERALS
  btsensor_nuttx_peripheral_stop();
#endif
  btsensor_tx_deinit();
  brickwright_hub_protocol_reset(&g_modern_protocol);
  btsensor_scheduler_release();
}

static int cmd_start(void)
{
  const struct btsensor_lifecycle_hooks hooks =
    {
      .receive = transport_receive,
      .state = transport_state,
      .services_start = services_start,
      .services_stop = services_stop,
    };
  int ret = btsensor_lifecycle_start(&hooks);
  if (ret < 0)
    {
      printf("btsensor: start failed: %d\n", ret);
      return 1;
    }

  printf("btsensor: started (pid %d)\n", ret);
  return 0;
}

static int cmd_stop(void)
{
  int ret = btsensor_lifecycle_stop(CONFIG_APP_BTSENSOR_STOP_TIMEOUT_MS);
  if (ret < 0)
    {
      printf("btsensor: stop failed: %d\n", ret);
      return 1;
    }

  printf("btsensor: stopped\n");
  return 0;
}

static int cmd_status(void)
{
  bool running = btsensor_lifecycle_running();
  printf("running: %s\n", running ? "yes" : "no");
  if (running)
    {
      printf("pid: %d\n", btsensor_lifecycle_pid());
      printf("classic: %s\n",
             btsensor_transport_connected(BRICKWRIGHT_HUB_LINK_CLASSIC) ?
             "connected" : "disconnected");
      printf("ble: %s\n",
             btsensor_transport_connected(BRICKWRIGHT_HUB_LINK_BLE) ?
             "connected" : "disconnected");
    }
  return 0;
}

static int cmd_bt(const char *value)
{
  bool visible;
  if (strcmp(value, "on") == 0)
    {
      visible = true;
    }
  else if (strcmp(value, "off") == 0)
    {
      visible = false;
    }
  else
    {
      printf("Usage: btsensor bt <on|off>\n");
      return 1;
    }

  int ret = btsensor_transport_set_visible(visible);
  if (ret < 0)
    {
      printf("btsensor: bt failed: %d\n", ret);
      return 1;
    }
  return 0;
}

static void usage(void)
{
  printf("Usage: btsensor <start|stop|status|bt on|bt off>\n");
}

int main(int argc, char **argv)
{
  if (argc == 2 && strcmp(argv[1], "start") == 0)
    {
      return cmd_start();
    }
  if (argc == 2 && strcmp(argv[1], "stop") == 0)
    {
      return cmd_stop();
    }
  if (argc == 2 && strcmp(argv[1], "status") == 0)
    {
      return cmd_status();
    }
  if (argc == 3 && strcmp(argv[1], "bt") == 0)
    {
      return cmd_bt(argv[2]);
    }

  usage();
  return 1;
}
