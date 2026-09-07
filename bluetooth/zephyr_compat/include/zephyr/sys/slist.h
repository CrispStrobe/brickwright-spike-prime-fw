/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRICKWRIGHT_ZEPHYR_SYS_SLIST_H
#define BRICKWRIGHT_ZEPHYR_SYS_SLIST_H

#include <stdbool.h>
#include <stddef.h>
#include <zephyr/sys/util.h>

typedef struct _sys_snode {
  struct _sys_snode *next;
} sys_snode_t;

typedef struct {
  sys_snode_t *head;
  sys_snode_t *tail;
} sys_slist_t;

#define SYS_SLIST_STATIC_INIT(list) { 0, 0 }

static inline void sys_slist_init(sys_slist_t *list) { list->head = list->tail = 0; }
static inline bool sys_slist_is_empty(const sys_slist_t *list) { return list->head == 0; }
static inline sys_snode_t *sys_slist_peek_head(const sys_slist_t *list) { return list->head; }
static inline sys_snode_t *sys_slist_peek_tail(const sys_slist_t *list) { return list->tail; }

static inline void sys_slist_append(sys_slist_t *list, sys_snode_t *node)
{
  node->next = 0;
  if (list->tail) list->tail->next = node; else list->head = node;
  list->tail = node;
}

static inline void sys_slist_prepend(sys_slist_t *list, sys_snode_t *node)
{
  node->next = list->head;
  list->head = node;
  if (!list->tail) list->tail = node;
}

static inline void sys_slist_insert(sys_slist_t *list, sys_snode_t *prev,
                                    sys_snode_t *node)
{
  if (!prev) { sys_slist_prepend(list, node); return; }
  node->next = prev->next;
  prev->next = node;
  if (list->tail == prev) list->tail = node;
}

static inline sys_snode_t *sys_slist_get(sys_slist_t *list)
{
  sys_snode_t *node = list->head;
  if (node) {
    list->head = node->next;
    if (!list->head) list->tail = 0;
    node->next = 0;
  }
  return node;
}

static inline sys_snode_t *sys_slist_get_not_empty(sys_slist_t *list)
{
  return sys_slist_get(list);
}

static inline bool sys_slist_find(const sys_slist_t *list,
                                  const sys_snode_t *node,
                                  sys_snode_t **previous)
{
  sys_snode_t *prior = 0;
  for (sys_snode_t *it = list->head; it; prior = it, it = it->next)
    if (it == node)
      {
        if (previous) *previous = prior;
        return true;
      }
  if (previous) *previous = prior;
  return false;
}

static inline bool sys_slist_find_and_remove(sys_slist_t *list, sys_snode_t *node)
{
  sys_snode_t *prev = 0;
  for (sys_snode_t *it = list->head; it; prev = it, it = it->next) {
    if (it == node) {
      if (prev) prev->next = it->next; else list->head = it->next;
      if (list->tail == it) list->tail = prev;
      it->next = 0;
      return true;
    }
  }
  return false;
}

static inline void sys_slist_remove(sys_slist_t *list, sys_snode_t *prev,
                                    sys_snode_t *node)
{
  if (prev) prev->next = node->next; else list->head = node->next;
  if (list->tail == node) list->tail = prev;
  node->next = 0;
}

#define SYS_SLIST_FOR_EACH_NODE(list, node) \
  for ((node) = (list)->head; (node); (node) = (node)->next)
#define SYS_SLIST_FOR_EACH_NODE_SAFE(list, node, tmp) \
  for ((node) = (list)->head; (node) && ((tmp) = (node)->next, 1); (node) = (tmp))
#define SYS_SLIST_FOR_EACH_CONTAINER(list, var, member) \
  for ((var) = (list)->head ? CONTAINER_OF((list)->head, __typeof__(*(var)), member) : 0; \
       (var); (var) = (var)->member.next ? CONTAINER_OF((var)->member.next, __typeof__(*(var)), member) : 0)
#define SYS_SLIST_FOR_EACH_CONTAINER_SAFE(list, var, tmp, member) \
  for ((var) = (list)->head ? CONTAINER_OF((list)->head, __typeof__(*(var)), member) : 0; \
       (var) && ((tmp) = (var)->member.next ? CONTAINER_OF((var)->member.next, __typeof__(*(var)), member) : 0, 1); \
       (var) = (tmp))

#endif
