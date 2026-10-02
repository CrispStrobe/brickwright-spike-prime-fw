/* SPDX-License-Identifier: BSD-3-Clause
 * Copyright (c) 2026 Brickwright contributors
 */
#include "service.h"
#include <stdio.h>
#include <string.h>
static int hex(char c) {
  if(c>='0' && c<='9')return c-'0';
  if(c>='a' && c<='f')return c-'a'+10;
  if(c>='A' && c<='F')return c-'A'+10;
  return -1;
}
int main(int argc,char **argv) {
  uint8_t packet[20],reply[20];size_t n,i;int rc;
  if(argc==2 && strcmp(argv[1],"serve")==0) {
    rc=bw_program_service_init();return rc<0 ? 1 : 0;
  }
  if(argc!=3 || strcmp(argv[1],"packet")!=0) {
    puts("usage: hubprogram serve | packet HEX (8..20 bytes)");return 1;
  }
  n=strlen(argv[2]);if(n<16 || n>40 || n%2)return 1;
  for(i=0;i<n/2;i++) {
    int a=hex(argv[2][2*i]),b=hex(argv[2][2*i+1]);if(a<0 || b<0)return 1;
    packet[i]=(uint8_t)(a*16+b);
  }
  memset(reply,0,sizeof(reply));rc=bw_program_service_request(1,packet,n/2,reply);
  printf("BWPR ");for(i=0;i<20;i++)printf("%02x",reply[i]);puts("");
  return rc<0 ? 1 : 0;
}
