# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
ifndef MICROPYTHON_TOP
$(error MICROPYTHON_TOP must name the verified local MicroPython checkout)
endif
vpath mpconfigport.h apps/hubprogram/micropython
PACKAGE_DIR = third_party/micropython-embed
CFLAGS += -Iapps/hubprogram/micropython
USER_C_MODULES = apps/hubprogram/micropython
include $(MICROPYTHON_TOP)/ports/embed/embed.mk
