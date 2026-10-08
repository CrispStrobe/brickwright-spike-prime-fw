/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 * Actual C request/mailbox core with host syscall doubles, not ARM execution.
 */
#define main request_fixture_main
#include "test_lumprequest.c"
#undef main
static void counters(const char *name)
{
  scenario = name; opens = closes = calls = 0;
}
static void submit(uint32_t seq, uint32_t version, uint32_t selector)
{
  g_bw_lump_request_mailbox.request_magic = UINT32_C(0x42574c52);
  g_bw_lump_request_mailbox.request_version = version;
  g_bw_lump_request_mailbox.request_selector = selector;
  g_bw_lump_request_mailbox.request_seq = seq;
  bw_lump_request_mailbox_step();
  assert(g_bw_lump_request_mailbox.reply_seq == seq);
  assert(g_bw_lump_request_mailbox.reply_selector == selector);
}
int main(void)
{
  counters("empty");
  bw_lump_request_mailbox_step(); assert(!opens);
  submit(1, 1, 0);
  assert(opens == 1 && calls == 1 && closes == 1);
  assert(g_bw_lump_request_mailbox.reply_result == 0);
  assert(g_bw_lump_request_mailbox.reply_publication_seq == 1);
  bw_lump_request_mailbox_step();
  assert(opens == 1 && calls == 1 && closes == 1);
  assert(g_bw_lump_request_mailbox.reply_result == 0);
  counters("observe-invalidated-reply"); submit(2, 1, 7);
  assert(opens == 1 && calls == 6 && closes == 1);
  assert(g_bw_lump_request_mailbox.reply_result == 0);
  assert(g_bw_lump_request_mailbox.reply_publication_seq == 2);
  assert(g_bw_lump_request.records[5].error == EAGAIN);
  counters("reject"); submit(3, 2, 0);
  assert(!opens && g_bw_lump_request_mailbox.reply_result == -EINVAL);
  assert(g_bw_lump_request_mailbox.reply_publication_seq == 0);
  submit(4, 1, 99); assert(!opens && g_bw_lump_request_mailbox.reply_result == -EINVAL);
  submit(6, 1, 0); assert(!opens && g_bw_lump_request_mailbox.reply_result == -EINVAL);
  counters("empty"); submit(7, 1, 1);
  assert(opens == 1 && calls == 1 && closes == 1);
  assert(g_bw_lump_request_mailbox.reply_result == 0);
  assert(g_bw_lump_request_mailbox.reply_publication_seq == 3);
  assert(g_bw_lump_request.records[0].length == 36);
  counters("open-fail"); submit(8, 1, 0);
  assert(opens == 1 && !calls && !closes);
  assert(g_bw_lump_request_mailbox.reply_result == -EBUSY);
  assert(g_bw_lump_request_mailbox.reply_publication_seq == 4);
  counters("reject"); g_request_busy = 1; submit(9, 1, 0);
  assert(!opens && g_bw_lump_request_mailbox.reply_result == -EBUSY);
  assert(!g_bw_lump_request_mailbox.reply_publication_seq);
  g_request_busy = 0; g_bw_lump_request.sequence = UINT32_MAX;
  submit(10, 1, 0);
  assert(!opens && g_bw_lump_request_mailbox.reply_result == -EOVERFLOW);
  assert(!g_bw_lump_request_mailbox.reply_publication_seq);
  g_bw_lump_request.sequence = 4;
  counters("close-fail"); submit(11, 1, 0);
  assert(opens == 1 && calls == 1 && closes == 1);
  assert(g_bw_lump_request_mailbox.reply_result == -EIO);
  assert(g_bw_lump_request_mailbox.reply_publication_seq == 5);
  counters("open-no-errno"); submit(12, 1, 0);
  assert(opens == 1 && !calls && !closes);
  assert(g_bw_lump_request_mailbox.reply_result == -EIO);
  assert(g_bw_lump_request.state == 3 && !g_bw_lump_request.open_error);
  counters("close-no-errno"); submit(13, 1, 0);
  assert(opens == 1 && calls == 1 && closes == 1);
  assert(g_bw_lump_request_mailbox.reply_result == -EIO);
  assert(g_bw_lump_request.close_result == -1 && !g_bw_lump_request.close_error);
  counters("reject");
  g_bw_lump_request_mailbox.request_magic = 0;
  g_bw_lump_request_mailbox.request_seq = 14;
  bw_lump_request_mailbox_step();
  assert(!opens && g_bw_lump_request_mailbox.reply_seq == 14);
  assert(g_bw_lump_request_mailbox.reply_result == -EINVAL);
  submit(UINT32_MAX, 1, 0);
  assert(!opens && g_bw_lump_request_mailbox.reply_result == -EINVAL);
  g_bw_lump_request_mailbox.request_seq = 1; bw_lump_request_mailbox_step();
  assert(!opens && g_bw_lump_request_mailbox.reply_seq == UINT32_MAX);
  /* Host-only initial-condition control for the last admissible ordinal. */
  g_bw_lump_request_mailbox.reply_seq = UINT32_MAX - 1;
  counters("empty"); submit(UINT32_MAX, 1, 0);
  assert(opens == 1 && calls == 1 && closes == 1);
  assert(g_bw_lump_request_mailbox.reply_result == 0);
  g_bw_lump_request_mailbox.request_seq = 0; bw_lump_request_mailbox_step();
  assert(g_bw_lump_request_mailbox.reply_seq == UINT32_MAX && calls == 1);
  /* Independent port dispatch controls, using a fresh host-only ordinal. */
  g_bw_lump_request_mailbox.request_seq = g_bw_lump_request_mailbox.reply_seq = 0;
  expected_path = "/dev/legoport4";
  counters("data"); submit(1, 1, 8);
  assert(opens == 1 && calls == 1 && closes == 1);
  assert(g_bw_lump_request.selector == 8 && g_bw_lump_request.records[0].result == 0);
  counters("data"); submit(2, 1, 9);
  assert(opens == 1 && calls == 6 && closes == 1);
  assert(g_bw_lump_request.selector == 9 && g_bw_lump_request.records[5].result == 0);
  counters("reject"); submit(3, 1, 10);
  assert(!opens && g_bw_lump_request_mailbox.reply_result == -EINVAL);
  puts("Request mailbox C controls PASS");
  return 0;
}
