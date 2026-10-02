# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Brickwright contributors
include $(APPDIR)/Make.defs
PROGNAME = hubprogram
PRIORITY = SCHED_PRIORITY_DEFAULT
STACKSIZE = 4096
MODULE = $(CONFIG_APP_HUBPROGRAM)
MAINSRC = hubprogram_main.c
CSRCS = program.c upload.c motor.c device.c service.c
BRICKWRIGHT_ROOT := $(abspath $(APPDIR)/..)
MICROPY_DIR := $(BRICKWRIGHT_ROOT)/third_party/micropython-embed
CSRCS += brickwright_module.c python_output.c
CSRCS += $(notdir $(wildcard $(MICROPY_DIR)/py/*.c))
CSRCS += $(filter-out mphalport.c,$(notdir $(wildcard $(MICROPY_DIR)/port/*.c)))
CSRCS += gchelper_generic.c
VPATH += :$(MICROPY_DIR)/py:$(MICROPY_DIR)/port:$(MICROPY_DIR)/shared/runtime:$(BRICKWRIGHT_ROOT)/apps/hubprogram/micropython
CFLAGS += -I$(MICROPY_DIR) -I$(MICROPY_DIR)/port -I$(BRICKWRIGHT_ROOT)/apps/hubprogram/micropython
# Keep the interpreter within the physical 640 KiB protected userspace flash.
CFLAGS += -Os
include $(APPDIR)/Application.mk
