/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_CONTROLLER_LIFECYCLE_H
#define BRICKWRIGHT_CONTROLLER_LIFECYCLE_H

#include <stdbool.h>
#include <stdint.h>

enum brickwright_controller_state
{
  BRICKWRIGHT_CONTROLLER_OFF,
  BRICKWRIGHT_CONTROLLER_STARTING,
  BRICKWRIGHT_CONTROLLER_READY,
  BRICKWRIGHT_CONTROLLER_RECOVERING,
  BRICKWRIGHT_CONTROLLER_FAILED
};

struct brickwright_controller_ops
{
  int (*power_cycle)(void *context);
  int (*open)(void *context, uint32_t baud);
  int (*load_firmware)(void *context);
  int (*set_controller_baud)(void *context, uint32_t baud);
  int (*set_host_baud)(void *context, uint32_t baud);
  int (*start_host)(void *context);
  int (*stop_host)(void *context);
  void (*close)(void *context);
};

struct brickwright_controller_config
{
  uint32_t boot_baud;
  uint32_t operational_baud;
  unsigned int max_recoveries;
};

struct brickwright_controller
{
  const struct brickwright_controller_ops *ops;
  void *context;
  struct brickwright_controller_config config;
  enum brickwright_controller_state state;
  unsigned int recoveries;
  bool transport_open;
  bool host_started;
};

int brickwright_controller_init(
  struct brickwright_controller *controller,
  const struct brickwright_controller_config *config,
  const struct brickwright_controller_ops *ops, void *context);
int brickwright_controller_start(struct brickwright_controller *controller);
int brickwright_controller_shutdown(struct brickwright_controller *controller);
int brickwright_controller_recover(struct brickwright_controller *controller);

struct brickwright_acl_credits
{
  unsigned int capacity;
  unsigned int available;
};

int brickwright_acl_credits_init(struct brickwright_acl_credits *credits,
                                 unsigned int capacity);
int brickwright_acl_credits_acquire(struct brickwright_acl_credits *credits);
int brickwright_acl_credits_complete(struct brickwright_acl_credits *credits,
                                    unsigned int count);
void brickwright_acl_credits_reset(struct brickwright_acl_credits *credits);

#endif
