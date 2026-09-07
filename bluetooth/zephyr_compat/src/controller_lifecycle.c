/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <string.h>
#include <brickwright/controller_lifecycle.h>

static int validate(const struct brickwright_controller_config *config,
                    const struct brickwright_controller_ops *ops)
{
  if (!config || !ops || !config->boot_baud || !config->operational_baud ||
      !ops->power_cycle || !ops->open || !ops->load_firmware ||
      !ops->set_controller_baud || !ops->set_host_baud || !ops->start_host ||
      !ops->stop_host || !ops->close)
    {
      return -EINVAL;
    }
  return 0;
}

static void unwind(struct brickwright_controller *controller)
{
  if (controller->host_started)
    {
      (void)controller->ops->stop_host(controller->context);
      controller->host_started = false;
    }
  if (controller->transport_open)
    {
      controller->ops->close(controller->context);
      controller->transport_open = false;
    }
}

static int bring_up(struct brickwright_controller *controller)
{
  int result = controller->ops->power_cycle(controller->context);
  if (result != 0)
    {
      return result;
    }
  result = controller->ops->open(controller->context,
                                 controller->config.boot_baud);
  if (result != 0)
    {
      return result;
    }
  controller->transport_open = true;
  result = controller->ops->load_firmware(controller->context);
  if (result == 0 &&
      controller->config.operational_baud != controller->config.boot_baud)
    {
      /* The controller must switch first.  If the host switch fails, the
       * next power cycle restores the controller's ROM baud. */
      result = controller->ops->set_controller_baud(
        controller->context, controller->config.operational_baud);
      if (result == 0)
        {
          result = controller->ops->set_host_baud(
            controller->context, controller->config.operational_baud);
        }
    }
  if (result == 0)
    {
      result = controller->ops->start_host(controller->context);
      controller->host_started = result == 0;
    }
  if (result != 0)
    {
      unwind(controller);
    }
  return result;
}

int brickwright_controller_init(
  struct brickwright_controller *controller,
  const struct brickwright_controller_config *config,
  const struct brickwright_controller_ops *ops, void *context)
{
  int result = controller ? validate(config, ops) : -EINVAL;
  if (result != 0)
    {
      return result;
    }
  memset(controller, 0, sizeof(*controller));
  controller->ops = ops;
  controller->context = context;
  controller->config = *config;
  controller->state = BRICKWRIGHT_CONTROLLER_OFF;
  return 0;
}

int brickwright_controller_start(struct brickwright_controller *controller)
{
  if (!controller || !controller->ops ||
      controller->state != BRICKWRIGHT_CONTROLLER_OFF)
    {
      return -EINVAL;
    }
  controller->state = BRICKWRIGHT_CONTROLLER_STARTING;
  int result = bring_up(controller);
  controller->state = result == 0 ? BRICKWRIGHT_CONTROLLER_READY :
                                    BRICKWRIGHT_CONTROLLER_FAILED;
  return result;
}

int brickwright_controller_shutdown(struct brickwright_controller *controller)
{
  if (!controller || !controller->ops)
    {
      return -EINVAL;
    }
  int result = 0;
  if (controller->host_started)
    {
      result = controller->ops->stop_host(controller->context);
      controller->host_started = false;
    }
  if (controller->transport_open)
    {
      controller->ops->close(controller->context);
      controller->transport_open = false;
    }
  controller->state = BRICKWRIGHT_CONTROLLER_OFF;
  return result;
}

int brickwright_controller_recover(struct brickwright_controller *controller)
{
  if (!controller || !controller->ops ||
      (controller->state != BRICKWRIGHT_CONTROLLER_READY &&
       controller->state != BRICKWRIGHT_CONTROLLER_FAILED))
    {
      return -EINVAL;
    }
  if (controller->recoveries >= controller->config.max_recoveries)
    {
      return -EAGAIN;
    }
  controller->state = BRICKWRIGHT_CONTROLLER_RECOVERING;
  unwind(controller);
  ++controller->recoveries;
  int result = bring_up(controller);
  controller->state = result == 0 ? BRICKWRIGHT_CONTROLLER_READY :
                                    BRICKWRIGHT_CONTROLLER_FAILED;
  return result;
}

int brickwright_acl_credits_init(struct brickwright_acl_credits *credits,
                                 unsigned int capacity)
{
  if (!credits || !capacity)
    {
      return -EINVAL;
    }
  credits->capacity = capacity;
  credits->available = capacity;
  return 0;
}

int brickwright_acl_credits_acquire(struct brickwright_acl_credits *credits)
{
  if (!credits || !credits->capacity)
    {
      return -EINVAL;
    }
  if (!credits->available)
    {
      return -EAGAIN;
    }
  --credits->available;
  return 0;
}

int brickwright_acl_credits_complete(struct brickwright_acl_credits *credits,
                                    unsigned int count)
{
  if (!credits || !credits->capacity ||
      count > credits->capacity - credits->available)
    {
      return -ERANGE;
    }
  credits->available += count;
  return 0;
}

void brickwright_acl_credits_reset(struct brickwright_acl_credits *credits)
{
  if (credits)
    {
      credits->available = credits->capacity;
    }
}
