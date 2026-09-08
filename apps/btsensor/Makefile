# SPDX-License-Identifier: Apache-2.0
include $(APPDIR)/Make.defs

PROGNAME  = btsensor
PRIORITY  = $(CONFIG_APP_BTSENSOR_PRIORITY)
STACKSIZE = $(CONFIG_APP_BTSENSOR_STACKSIZE)
MODULE    = $(CONFIG_APP_BTSENSOR)

MAINSRC = btsensor_main.c

# Bluetooth ownership lives in btsensor_lifecycle and the narrow transport
# adapter. Only stack-neutral sources are active in this checkpoint.
CSRCS += btsensor_lifecycle.c btsensor_transport.c
CSRCS += btsensor_tx.c btsensor_cmd_neutral.c btsensor_classic.c
CSRCS += btsensor_modern.c btsensor_modern_backend.c btsensor_modern_notify.c
CSRCS += btsensor_scheduler.c btsensor_sound.c
CSRCS += hub_protocol.c spike_codec.c
ifneq ($(CONFIG_APP_BTSENSOR_VIRTUAL_CONTROLLER),y)
CSRCS += btsensor_ti_payload.c
endif

ifeq ($(CONFIG_APP_BTSENSOR_NUTTX_PERIPHERALS),y)
CSRCS += bundle_emitter.c
CSRCS += imu_sampler.c sensor_sampler.c btsensor_nuttx_peripheral.c
CSRCS += btsensor_nuttx_snapshot.c
endif

# The imported Apache Zephyr host and its pinned Mbed TLS crypto dependency are
# one archive. Keeping it separate avoids source-basename collisions and
# prevents application-local controller firmware or BTstack copies returning.
CFLAGS += -I$(APPDIR)/external/btsensor
CFLAGS += -I$(APPDIR)/../bluetooth/zephyr_compat/include
CFLAGS += -include zephyr/autoconf.h
CFLAGS += -I$(APPDIR)/../third_party/zephyr-host/upstream/include
CFLAGS += -I$(APPDIR)/../third_party/zephyr-host/upstream/subsys/bluetooth
CFLAGS += -I$(APPDIR)/../bluetooth/daemon
CFLAGS += -I$(APPDIR)/../protocol/c
CFLAGS += -I$(APPDIR)/../bluetooth/ti_service_pack
CFLAGS += -I$(APPDIR)/../.local/ti/cc2564c
VPATH += :$(APPDIR)/../bluetooth/daemon
VPATH += :$(APPDIR)/../protocol/c
VPATH += :$(APPDIR)/../bluetooth/ti_service_pack

BRICKWRIGHT_ROOT := $(abspath $(APPDIR)/..)
BRICKWRIGHT_BT_LIBDIR := $(BRICKWRIGHT_ROOT)/build/nuttx-bluetooth
BRICKWRIGHT_BT_LIB := $(BRICKWRIGHT_BT_LIBDIR)/libbrickwright_zephyr_host.a
BRICKWRIGHT_TI_PAYLOAD := \
  $(BRICKWRIGHT_ROOT)/.local/ti/cc2564c/ti_bts_local_payload.h
BRICKWRIGHT_TI_VENDOR_DIR := $(BRICKWRIGHT_ROOT)/third_party/ti-cc2564c
BRICKWRIGHT_TI_VENDOR_BTS := \
  $(BRICKWRIGHT_TI_VENDOR_DIR)/TIInit_6.12.26.bts
BRICKWRIGHT_BT_INPUTS := \
  $(BRICKWRIGHT_ROOT)/tools/build_zephyr_nuttx_archive.sh \
  $(BRICKWRIGHT_ROOT)/tools/zephyr_nuttx_sources.sh \
  $(shell find $(BRICKWRIGHT_ROOT)/bluetooth/zephyr_compat \
    $(BRICKWRIGHT_ROOT)/third_party/zephyr-host/upstream -type f)

$(BRICKWRIGHT_BT_LIB): $(BRICKWRIGHT_BT_INPUTS)
	$(Q)CROSS_COMPILE=$(CROSSDEV) \
	  NUTTX_CONFIG=$(TOPDIR)/include/nuttx/config.h \
	  $(BRICKWRIGHT_ROOT)/tools/build_zephyr_nuttx_archive.sh $@

all:: $(BRICKWRIGHT_BT_LIB)

$(BRICKWRIGHT_TI_PAYLOAD): $(BRICKWRIGHT_TI_VENDOR_BTS) \
    $(BRICKWRIGHT_TI_VENDOR_DIR)/LICENSE.ti \
    $(BRICKWRIGHT_ROOT)/tools/import_ti_service_pack.py \
    $(BRICKWRIGHT_ROOT)/policy/ti-service-packs.json
	$(Q)python3 $(BRICKWRIGHT_ROOT)/tools/import_ti_service_pack.py \
	  $(BRICKWRIGHT_TI_VENDOR_BTS) \
	  --license $(BRICKWRIGHT_TI_VENDOR_DIR)/LICENSE.ti

ifneq ($(CONFIG_APP_BTSENSOR_VIRTUAL_CONTROLLER),y)
all:: $(BRICKWRIGHT_TI_PAYLOAD)
endif

include $(APPDIR)/Application.mk

ifneq ($(CONFIG_APP_BTSENSOR_VIRTUAL_CONTROLLER),y)
# If an import appears after a previous payload-free build, its newer
# timestamp must force the permissive provider shim to be recompiled.
$(filter %btsensor_ti_payload%,$(COBJS)): $(BRICKWRIGHT_TI_PAYLOAD)
endif

# Application.mk first places libapps and libgcc in LDLIBS. The Bluetooth
# archive follows them inside the same start-group, so circular references
# among the app, Zephyr host and Mbed TLS resolve without order assumptions.
LDLIBS += $(BRICKWRIGHT_BT_LIB)
$(PROGLIST): $(BRICKWRIGHT_BT_LIB)

clean::
	$(call DELDIR,$(BRICKWRIGHT_BT_LIBDIR))
