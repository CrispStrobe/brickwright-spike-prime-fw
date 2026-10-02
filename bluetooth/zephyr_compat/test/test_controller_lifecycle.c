/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>
#include <brickwright/controller_lifecycle.h>

enum operation
{
  OP_POWER = 1,
  OP_OPEN,
  OP_LOAD,
  OP_CONTROLLER_BAUD,
  OP_HOST_BAUD,
  OP_HOST_START,
  OP_HOST_STOP,
  OP_CLOSE
};

struct fixture
{
  enum operation log[64];
  unsigned int log_length;
  enum operation fail;
  uint32_t opened_baud;
  uint32_t controller_baud;
  uint32_t host_baud;
  uint32_t persisted_pairing_marker;
};

static int record(struct fixture *fixture, enum operation operation)
{
  assert(fixture->log_length < sizeof(fixture->log) / sizeof(fixture->log[0]));
  fixture->log[fixture->log_length++] = operation;
  return fixture->fail == operation ? -EIO : 0;
}

static int power_cycle(void *context)
{
  return record(context, OP_POWER);
}

static int open_transport(void *context, uint32_t baud)
{
  struct fixture *fixture = context;
  fixture->opened_baud = baud;
  return record(fixture, OP_OPEN);
}

static int load_firmware(void *context)
{
  return record(context, OP_LOAD);
}

static int set_controller_baud(void *context, uint32_t baud)
{
  struct fixture *fixture = context;
  fixture->controller_baud = baud;
  return record(fixture, OP_CONTROLLER_BAUD);
}

static int set_host_baud(void *context, uint32_t baud)
{
  struct fixture *fixture = context;
  fixture->host_baud = baud;
  return record(fixture, OP_HOST_BAUD);
}

static int start_host(void *context)
{
  return record(context, OP_HOST_START);
}

static int stop_host(void *context)
{
  return record(context, OP_HOST_STOP);
}

static void close_transport(void *context)
{
  (void)record(context, OP_CLOSE);
}

static const struct brickwright_controller_ops ops = {
  .power_cycle = power_cycle,
  .open = open_transport,
  .load_firmware = load_firmware,
  .set_controller_baud = set_controller_baud,
  .set_host_baud = set_host_baud,
  .start_host = start_host,
  .stop_host = stop_host,
  .close = close_transport
};

static const struct brickwright_controller_config config = {
  .boot_baud = 115200,
  .operational_baud = 3000000,
  .max_recoveries = 2
};

static void expect_log(const struct fixture *fixture,
                       const enum operation *expected, size_t length)
{
  assert(fixture->log_length == length);
  assert(memcmp(fixture->log, expected, length * sizeof(expected[0])) == 0);
}

static void test_start_shutdown_and_recovery(void)
{
  struct fixture fixture = {.persisted_pairing_marker = 0x51a7e001};
  struct brickwright_controller controller;
  assert(brickwright_controller_init(&controller, &config, &ops, &fixture) == 0);
  assert(brickwright_controller_start(&controller) == 0);
  assert(controller.state == BRICKWRIGHT_CONTROLLER_READY);
  assert(fixture.opened_baud == config.boot_baud);
  assert(fixture.controller_baud == config.operational_baud);
  assert(fixture.host_baud == config.operational_baud);
  const enum operation start[] = {
    OP_POWER, OP_OPEN, OP_LOAD, OP_CONTROLLER_BAUD, OP_HOST_BAUD, OP_HOST_START
  };
  expect_log(&fixture, start, sizeof(start) / sizeof(start[0]));

  assert(brickwright_controller_recover(&controller) == 0);
  assert(controller.state == BRICKWRIGHT_CONTROLLER_READY);
  assert(controller.recoveries == 1);
  assert(fixture.persisted_pairing_marker == 0x51a7e001);
  assert(fixture.log[6] == OP_HOST_STOP && fixture.log[7] == OP_CLOSE &&
         fixture.log[8] == OP_POWER);
  assert(brickwright_controller_recover(&controller) == 0);
  assert(brickwright_controller_recover(&controller) == -EAGAIN);
  assert(brickwright_controller_shutdown(&controller) == 0);
  assert(controller.state == BRICKWRIGHT_CONTROLLER_OFF);
  unsigned int after_shutdown = fixture.log_length;
  assert(brickwright_controller_shutdown(&controller) == 0);
  assert(fixture.log_length == after_shutdown);
}

static void test_bringup_failures_unwind(void)
{
  const enum operation failures[] = {
    OP_POWER, OP_OPEN, OP_LOAD, OP_CONTROLLER_BAUD, OP_HOST_BAUD, OP_HOST_START
  };
  for (size_t i = 0; i < sizeof(failures) / sizeof(failures[0]); ++i)
    {
      struct fixture fixture = {.fail = failures[i]};
      struct brickwright_controller controller;
      assert(brickwright_controller_init(&controller, &config, &ops,
                                         &fixture) == 0);
      assert(brickwright_controller_start(&controller) == -EIO);
      assert(controller.state == BRICKWRIGHT_CONTROLLER_FAILED);
      assert(!controller.transport_open && !controller.host_started);
      if (failures[i] >= OP_LOAD)
        {
          assert(fixture.log[fixture.log_length - 1] == OP_CLOSE);
        }
      assert(brickwright_controller_recover(&controller) == -EIO);
      assert(controller.recoveries == 1);
    }
}

static void test_same_baud_skips_switch(void)
{
  struct fixture fixture = {0};
  struct brickwright_controller controller;
  struct brickwright_controller_config same = config;
  same.operational_baud = same.boot_baud;
  assert(brickwright_controller_init(&controller, &same, &ops, &fixture) == 0);
  assert(brickwright_controller_start(&controller) == 0);
  const enum operation expected[] = {OP_POWER, OP_OPEN, OP_LOAD, OP_HOST_START};
  expect_log(&fixture, expected, sizeof(expected) / sizeof(expected[0]));
  assert(brickwright_controller_shutdown(&controller) == 0);
}

static void test_acl_credit_flow_and_power_cycle_reset(void)
{
  struct brickwright_acl_credits credits;
  assert(brickwright_acl_credits_init(&credits, 4) == 0);
  for (unsigned int i = 0; i < 4; ++i)
    {
      assert(brickwright_acl_credits_acquire(&credits) == 0);
    }
  assert(brickwright_acl_credits_acquire(&credits) == -EAGAIN);
  assert(brickwright_acl_credits_complete(&credits, 2) == 0);
  assert(brickwright_acl_credits_acquire(&credits) == 0);
  assert(brickwright_acl_credits_complete(&credits, 4) == -ERANGE);
  assert(credits.available == 1);
  brickwright_acl_credits_reset(&credits);
  assert(credits.available == 4);
  assert(brickwright_acl_credits_complete(&credits, 1) == -ERANGE);
}

int main(void)
{
  test_start_shutdown_and_recovery();
  test_bringup_failures_unwind();
  test_same_baud_skips_switch();
  test_acl_credit_flow_and_power_cycle_reset();
  return 0;
}
