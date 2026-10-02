############################################################################
# boards/spike-prime-hub/src/Makefile
############################################################################

include $(TOPDIR)/Make.defs

include Make.defs

# The generic generator depends on host directory enumeration order.
# Keep generated init sources reproducible across fresh checkouts.
GENROMFS = python3 $(BOARD_DIR)/../../tools/make_romfs.py

include $(TOPDIR)/boards/Board.mk

ifneq ($(RCSRCS)$(RCRAWS),)
$(ETCSRC): $(BOARD_DIR)/../../tools/make_romfs.py
endif

ARCHSRCDIR = $(TOPDIR)$(DELIM)arch$(DELIM)$(CONFIG_ARCH)$(DELIM)src
BOARDDIR = $(ARCHSRCDIR)$(DELIM)board
CFLAGS += ${INCDIR_PREFIX}$(BOARDDIR)$(DELIM)include
