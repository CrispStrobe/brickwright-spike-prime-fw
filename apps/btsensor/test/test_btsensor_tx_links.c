/* SPDX-License-Identifier: BSD-3-Clause */
/* Copyright (c) 2026 Brickwright contributors */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <brickwright/hub_transport.h>
#include "btsensor_tx.h"

struct sent { enum brickwright_hub_link link; char text[32]; };
static struct sent observed[32];
static unsigned count;
static int refusal[2];
static bool change_session, reenter;

bool brickwright_hub_transport_connected(enum brickwright_hub_link link)
{ (void)link; return true; }
int brickwright_hub_transport_send(enum brickwright_hub_link link, const void *data, size_t length)
{
  if (reenter)
    {
      reenter = false;
      btsensor_tx_on_can_send_now();
      return -EAGAIN;
    }
  if (refusal[link]) return refusal[link];
  assert(count < 32 && length < sizeof(observed[0].text));
  observed[count].link = link;
  memcpy(observed[count].text, data, length);
  observed[count++].text[length] = 0;
  if (change_session)
    {
      change_session = false;
      btsensor_tx_link_state(link, false, 1);
      btsensor_tx_link_state(link, true, 2);
      assert(btsensor_tx_enqueue_response_for_link(link, "NEW") == 0);
    }
  return 0;
}

static void reset(void)
{
  btsensor_tx_deinit();
  btsensor_tx_init();
  memset(observed, 0, sizeof(observed));
  count = 0;
  refusal[0] = refusal[1] = -EAGAIN;
  change_session = reenter = false;
  btsensor_tx_link_state(BRICKWRIGHT_HUB_LINK_CLASSIC, true, 1);
  btsensor_tx_link_state(BRICKWRIGHT_HUB_LINK_BLE, true, 1);
}

int main(void)
{
  const enum brickwright_hub_link classic = BRICKWRIGHT_HUB_LINK_CLASSIC;
  const enum brickwright_hub_link ble = BRICKWRIGHT_HUB_LINK_BLE;
  reset();
  assert(btsensor_tx_try_enqueue_frame_for_link(ble, (const uint8_t *)"BLE-F", 5) == 0);
  assert(btsensor_tx_enqueue_response_for_link(ble, "BLE-R") == 0);
  assert(btsensor_tx_enqueue_response_for_link(classic, "CLASSIC-R") == 0);
  btsensor_tx_set_link(classic, true);
  btsensor_tx_set_link(ble, true);
  assert(btsensor_tx_get_rfcomm_cid() == 1);
  refusal[classic] = 0;
  btsensor_tx_on_can_send_now();
  assert(count == 1 && observed[0].link == classic && !strcmp(observed[0].text, "CLASSIC-R"));
  refusal[ble] = 0;
  btsensor_tx_on_can_send_now();
  assert(count == 3 && observed[1].link == ble && !strcmp(observed[1].text, "BLE-R"));
  assert(observed[2].link == ble && !strcmp(observed[2].text, "BLE-F"));

  reset();
  assert(btsensor_tx_enqueue_response_for_link(ble, "STALE") == 0);
  assert(btsensor_tx_enqueue_response_for_link(classic, "KEEP") == 0);
  btsensor_tx_link_state(ble, false, 1);
  assert(btsensor_tx_try_enqueue_frame_for_link(ble, (const uint8_t *)"X", 1) == -ENOTCONN);
  btsensor_tx_link_state(ble, true, 2);
  refusal[0] = refusal[1] = 0;
  btsensor_tx_on_can_send_now();
  assert(count == 1 && observed[0].link == classic && !strcmp(observed[0].text, "KEEP"));
  assert(btsensor_tx_enqueue_response_for_link(ble, "NEW-BLE") == 0);
  assert(count == 2 && observed[1].link == ble && !strcmp(observed[1].text, "NEW-BLE"));

  reset();
  assert(btsensor_tx_enqueue_response_for_link(ble, "STALE-GENERATION") == 0);
  btsensor_tx_link_state(ble, true, 2);
  refusal[ble] = 0;
  btsensor_tx_on_can_send_now();
  assert(count == 0 && btsensor_tx_response_queue_empty());

  reset();
  assert(btsensor_tx_enqueue_response_for_link(classic, "OLD") == 0);
  change_session = true;
  refusal[classic] = 0;
  btsensor_tx_on_can_send_now();
  assert(count == 2 && !strcmp(observed[0].text, "OLD") && !strcmp(observed[1].text, "NEW"));
  assert(btsensor_tx_response_queue_empty());

  reset();
  assert(btsensor_tx_enqueue_response_for_link(classic, "RETRY") == 0);
  refusal[classic] = 0;
  reenter = true;
  btsensor_tx_on_can_send_now();
  assert(count == 1 && !strcmp(observed[0].text, "RETRY"));
  assert(btsensor_tx_response_queue_empty());
  puts("TX link destination, back-pressure, generation and reentry controls passed");
  return 0;
}
