# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

.PHONY: all build-kernel test clean check fmt docker-run

all:

KSOURCE := ${PWD}
ROADTEST_DIR = ${CURDIR}
ROADTEST_BUILD_DIR := ${KSOURCE}/.roadtest
KHEADERS := ${ROADTEST_BUILD_DIR}/usr
KMODULES := ${ROADTEST_BUILD_DIR}/modules

ifeq (${KSOURCE},${ROADTEST_DIR})
# Make make from the standard roadtest directory work without having to set
# additional variables.
KSOURCE=$(ROADTEST_DIR:/tools/testing/roadtest=)
endif

CFLAGS += -g -D_GNU_SOURCE=1 -Wall -Werror -std=gnu99 \
			-I${KSOURCE}/tools/include/ \
			-I${KHEADERS}/include/ \
			-I${ROADTEST_DIR}/src/libvhost-user/ \
			$(shell python3-config --embed --includes) -O2

${ROADTEST_BUILD_DIR}/roadtest-backend: ${ROADTEST_BUILD_DIR}/backend.o ${ROADTEST_BUILD_DIR}/libvhost-user.o
	$(CC) -o $@ $^ $(shell python3-config --embed --libs)
	# For the benefit of clangd
	echo ${CFLAGS} | tr " " "\n" > ${ROADTEST_DIR}/src/compile_flags.txt

${ROADTEST_BUILD_DIR}/backend.o: src/backend.c
	$(CC) -c -o $@ $(CFLAGS) $<

${ROADTEST_BUILD_DIR}/libvhost-user.o: src/libvhost-user/libvhost-user.c
	$(CC) -c -o $@ $(CFLAGS) $<

clean:
	rm -rf ${ROADTEST_BUILD_DIR} .docker_built

ifeq ($(DOCKER),1)
.docker_built: Dockerfile requirements.txt
	docker build --network=host -t roadtest ${ROADTEST_DIR}
	touch $@

# --network=host allows UML's con=port:... to work seamlessly
docker-run: .docker_built
	mkdir -p ${ROADTEST_BUILD_DIR}/umltmp
	docker run --network=host ${DOCKEROPTS} --user $(shell id -u ${USER}):$(shell id -g ${USER}) --interactive --tty --rm -v ${KSOURCE}:${KSOURCE} -w ${KSOURCE} --env TMPDIR=${ROADTEST_BUILD_DIR}/umltmp roadtest sh -c '${MAKE} -C ${ROADTEST_DIR} -${MAKEFLAGS} ${MAKECMDGOALS} DOCKER=0'

all test build-kernel check fmt: docker-run
	@:
else
all: test

ifneq ($(KBUILD),0)
# Calling make on the kernel is slow even if there is nothing to be rebuilt.
# Allow the user to avoid it with KBUILD=0
${ROADTEST_BUILD_DIR}/backend.o: build-kernel
${ROADTEST_BUILD_DIR}/libvhost-user.o: build-kernel
test: build-kernel
endif

build-kernel:
	mkdir -p ${ROADTEST_BUILD_DIR}
	find ${ROADTEST_DIR}/roadtest/tests/ -type f -name config | xargs cat > ${ROADTEST_BUILD_DIR}/.config
	${MAKE} -C ${KSOURCE} ARCH=um O=${ROADTEST_BUILD_DIR} olddefconfig
	${MAKE} -C ${KSOURCE} ARCH=um O=${ROADTEST_BUILD_DIR}
	${MAKE} -C ${KSOURCE} ARCH=um O=${ROADTEST_BUILD_DIR} INSTALL_HDR_PATH=${KHEADERS} headers_install
	${MAKE} -C ${KSOURCE} ARCH=um O=${ROADTEST_BUILD_DIR} INSTALL_MOD_PATH=${KMODULES} modules_install

test: ${ROADTEST_BUILD_DIR}/roadtest-backend
	python3 -m roadtest.cmd.main --ksrc-dir ${KSOURCE} --build-dir ${ROADTEST_BUILD_DIR} --work-dir ${ROADTEST_BUILD_DIR}/roadtest-work/ ${OPTS}

check:
	mypy --no-error-summary roadtest
	pyflakes roadtest
	black --check roadtest
	isort --profile black --check roadtest

fmt:
	black roadtest
	isort --profile black roadtest

endif
