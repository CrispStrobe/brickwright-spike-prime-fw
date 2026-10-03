/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors */
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <zephyr/bluetooth/crypto.h>
int bt_crypto_init(void);
/* These logging/unused RNG stubs keep this a focused crypto-boundary test. */
int bt_hci_le_rand(void *p, size_t n) {(void)p;(void)n; return -1;}
const char *bt_hex(const void *p, size_t n) {(void)p;(void)n;return "probe";}
static pthread_mutex_t gate=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t go=PTHREAD_COND_INITIALIZER;
static int ready;
static atomic_int failures;
static const uint8_t keys[2][16]={{0},{0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15}};
static const uint8_t input[2][16]={{0},{0,0x11,0x22,0x33,0x44,0x55,0x66,0x77,0x88,0x99,0xaa,0xbb,0xcc,0xdd,0xee,0xff}};
static const uint8_t expected[2][16]={{0x66,0xe9,0x4b,0xd4,0xef,0x8a,0x2c,0x3b,0x88,0x4c,0xfa,0x59,0xca,0x34,0x2b,0x2e},{0x69,0xc4,0xe0,0xd8,0x6a,0x7b,4,0x30,0xd8,0xcd,0xb7,0x80,0x70,0xb4,0xc5,0x5a}};
static void *worker(void *opaque) {
 intptr_t id=(intptr_t)opaque % 2;
 pthread_mutex_lock(&gate);ready++;pthread_cond_broadcast(&go);
 while(ready<8)pthread_cond_wait(&go,&gate);pthread_mutex_unlock(&gate);
 for(unsigned i=0;i<20000&&!atomic_load(&failures);i++) {
  uint8_t output[16], key[16], plain[16], want[16];
  for(unsigned j=0;j<16;j++) {
   key[j]=keys[id][15-j];plain[j]=input[id][15-j];want[j]=expected[id][15-j];
  }
  int rc=bt_encrypt_le(key,plain,output);
  if(rc||memcmp(output,want,16)) {
   fprintf(stderr,"PSA concurrent little-endian AES failure thread=%ld iteration=%u rc=%d\n",(long)id,i,rc);
   atomic_fetch_add(&failures,1);break;
  }
  rc=bt_encrypt_be(keys[id],input[id],output);
  if(rc||memcmp(output,expected[id],16)) {
   fprintf(stderr,"PSA concurrent AES failure thread=%ld iteration=%u rc=%d\n",(long)id,i,rc);
   atomic_fetch_add(&failures,1);break;
  }
 }
 return NULL;
}
int main(void) {
 assert(bt_crypto_init()==0);pthread_t threads[8];
 for(intptr_t i=0;i<8;i++)assert(pthread_create(&threads[i],NULL,worker,(void*)i)==0);
 for(unsigned i=0;i<8;i++)pthread_join(threads[i],NULL);
 if(atomic_load(&failures))return 1;
 puts("320000 concurrent actual bt_encrypt_le/be known-vector operations passed");return 0;
}
