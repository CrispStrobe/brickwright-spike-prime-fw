/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <time.h>
#include <zephyr/net_buf.h>

NET_BUF_POOL_FIXED_DEFINE(test_pool, 2, 32, 4, NULL);

struct wait_item { void *next; };
struct wait_context { struct k_lifo *lifo; struct wait_item *item; };

static void *delayed_put(void *opaque)
{
  struct wait_context *context = opaque;
  struct timespec delay = { .tv_nsec = 5 * 1000 * 1000 };
  nanosleep(&delay, NULL);
  k_lifo_put(context->lifo, context->item);
  return NULL;
}

int main(void)
{
  struct net_buf *first = net_buf_alloc(&test_pool, K_NO_WAIT);
  struct net_buf *second = net_buf_alloc(&test_pool, K_NO_WAIT);
  assert(first && second);
  assert(net_buf_alloc(&test_pool, K_NO_WAIT) == NULL);
  assert(first->ref == 1 && first->size == 32 && first->len == 0);

  net_buf_reserve(first, 4);
  net_buf_add_le16(first, 0x1234);
  assert(net_buf_headroom(first) == 4);
  assert(net_buf_frags_len(first) == 2);

  assert(net_buf_ref(first) == first && first->ref == 2);
  net_buf_unref(first);
  assert(first->ref == 1);
  net_buf_unref(first);

  first = net_buf_alloc(&test_pool, K_NO_WAIT);
  assert(first);
  net_buf_add_u8(first, 0xaa);
  net_buf_add_u8(second, 0xbb);
  net_buf_frag_add(first, second);
  assert(net_buf_frags_len(first) == 2);
  assert(net_buf_frag_last(first) == second);
  net_buf_unref(first);

  first = net_buf_alloc(&test_pool, K_NO_WAIT);
  second = net_buf_alloc(&test_pool, K_NO_WAIT);
  assert(first && second);
  net_buf_unref(first);
  net_buf_unref(second);

  struct k_lifo lifo = Z_LIFO_INITIALIZER(lifo);
  struct wait_item item = {0};
  struct wait_context context = { .lifo = &lifo, .item = &item };
  pthread_t producer;
  assert(pthread_create(&producer, NULL, delayed_put, &context) == 0);
  assert(k_lifo_get(&lifo, 100) == &item);
  assert(pthread_join(producer, NULL) == 0);
  assert(k_lifo_get(&lifo, K_NO_WAIT) == NULL);
  return 0;
}
