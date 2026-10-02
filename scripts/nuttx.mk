DOCKER_IMAGE  := nuttx-builder
MAKEOPTS      := -j$(shell nproc 2>/dev/null || echo 2)
BOARD         ?= spike-prime-hub
BOARD_CONFIG  ?= simulation

# out-of-tree board: if boards/<BOARD> exists, use path-based configure
ifneq ($(wildcard $(CURDIR)/boards/$(BOARD)),)
  CONFIGURE_ARG = ../boards/$(BOARD)/configs/$(BOARD_CONFIG)
else
  CONFIGURE_ARG = $(BOARD):$(BOARD_CONFIG)
endif

DOCKER_RUN := docker run --rm \
	--user "$(shell id -u):$(shell id -g)" \
	-v /etc/passwd:/etc/passwd:ro \
	-v /etc/group:/etc/group:ro \
	-v "$(CURDIR):$(CURDIR)" \
	-w "$(CURDIR)/nuttx" \
	$(DOCKER_IMAGE)

DOCKER_RUN_IT := docker run --rm -it \
	--user "$(shell id -u):$(shell id -g)" \
	-v /etc/passwd:/etc/passwd:ro \
	-v /etc/group:/etc/group:ro \
	-v "$(CURDIR):$(CURDIR)" \
	-w "$(CURDIR)/nuttx" \
	$(DOCKER_IMAGE)

.PHONY: build configure clean distclean docker-build submodules \
        menuconfig savedefconfig backports

build: docker-build link-apps configure
	python3 tools/check_reuse_licenses.py
ifeq ($(BOARD):$(BOARD_CONFIG),spike-prime-hub:simulation)
	python3 tools/check_firmware_inputs.py --config-only --config nuttx/.config
endif
	$(DOCKER_RUN) make $(MAKEOPTS)
ifeq ($(BOARD):$(BOARD_CONFIG),spike-prime-hub:simulation)
	$(DOCKER_RUN) bash ../tools/check_simulation_firmware.sh
endif

# Symlink project-local apps/ into nuttx-apps/external for build integration
link-apps:
	@if [ -d $(CURDIR)/apps ] && [ ! -e $(CURDIR)/nuttx-apps/external ]; then \
		ln -s $(CURDIR)/apps $(CURDIR)/nuttx-apps/external; \
	fi

nuttx/Makefile:
	git submodule update --init nuttx nuttx-apps

submodules: nuttx/Makefile

docker-build: nuttx/Makefile
	@if [ -z "$$(docker images -q $(DOCKER_IMAGE) 2>/dev/null)" ]; then \
		docker build -t $(DOCKER_IMAGE) -f docker/Dockerfile.nuttx docker; \
	fi

backports: nuttx/Makefile
	python3 tools/apply_nuttx_backports.py

configure: docker-build backports
	@if [ ! -f nuttx/.config ]; then \
		$(DOCKER_RUN) ./tools/configure.sh -l -a ../nuttx-apps $(CONFIGURE_ARG); \
	fi

menuconfig: docker-build
	$(DOCKER_RUN_IT) make menuconfig

savedefconfig: docker-build
	$(DOCKER_RUN) make savedefconfig

# --- Clean ---

clean:
	-$(DOCKER_RUN) make clean

distclean:
	-$(DOCKER_RUN) make distclean
