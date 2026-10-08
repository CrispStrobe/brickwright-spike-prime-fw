include $(APPDIR)/Make.defs

PROGNAME = port
PRIORITY = SCHED_PRIORITY_DEFAULT
STACKSIZE = $(CONFIG_DEFAULT_TASK_STACKSIZE)
MODULE = $(CONFIG_APP_PORT)

MAINSRC = port_main.c

# Diagnostic code is absent from hardware builds. No new Kconfig selection.
ifeq ($(CONFIG_APP_BTSENSOR_SIM_NO_SERVICE_PACK)$(CONFIG_BUILD_PROTECTED)$(CONFIG_LEGO_LUMP),yyy)
CSRCS += lumpprobe.c
endif

include $(APPDIR)/Application.mk
