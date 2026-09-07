.DEFAULT_GOAL := nuttx

.PHONY: nuttx nuttx-% clean distclean help

# NuttX targets
BOARD        ?= spike-prime-hub
BOARD_CONFIG ?= usbnsh

nuttx:
	$(MAKE) -f scripts/nuttx.mk build BOARD=$(BOARD) BOARD_CONFIG=$(BOARD_CONFIG)

nuttx-%:
	$(MAKE) -f scripts/nuttx.mk $* BOARD=$(BOARD) BOARD_CONFIG=$(BOARD_CONFIG)

# Aggregate targets
clean:
	-$(MAKE) -f scripts/nuttx.mk clean

distclean:
	-$(MAKE) -f scripts/nuttx.mk distclean
	-docker rmi nuttx-builder
	-git submodule deinit -f nuttx
	-git submodule deinit -f nuttx-apps

help:
	@echo "Usage:"
	@echo "  make nuttx                          Build NuttX firmware (SPIKE Prime Hub)"
	@echo "  make nuttx-configure                Configure NuttX"
	@echo "  make nuttx-menuconfig               Open NuttX Kconfig menu"
	@echo "  make nuttx-savedefconfig             Save NuttX defconfig"
	@echo "  make nuttx-clean                    Clean NuttX build artifacts"
	@echo "  make nuttx-distclean                NuttX distclean (remove .config)"
	@echo ""
	@echo "  make clean                          Clean all builds"
	@echo "  make distclean                      Full clean (docker rmi + submodule deinit)"
