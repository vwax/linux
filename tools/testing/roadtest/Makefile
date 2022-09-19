# SPDX-License-Identifier: GPL-2.0-only
# Copyright Axis Communications AB

.PHONY: all build-kernel test clean check fmt

all:

KSOURCE := ${PWD}
ROADTEST_DIR = ${CURDIR}

ifeq (${KSOURCE},${ROADTEST_DIR})
# Make make from the standard roadtest directory work without having to set
# additional variables.
KSOURCE=$(ROADTEST_DIR:/tools/testing/roadtest=)
endif

ROADTEST_BUILD_DIR := ${KSOURCE}/.roadtest
KHEADERS := ${ROADTEST_BUILD_DIR}/usr
KMODULES := ${ROADTEST_BUILD_DIR}/modules
ROADTEST_VENV := ${KSOURCE}/venv
# Enable gcov coverage for full kernel.  Not enabled by default since it
# slows down testing and, unlike other debug options which slow testing,
# needs manual inspecting to have a benefit.
COV := 0

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
	rm -rf ${ROADTEST_BUILD_DIR}

all: test

${ROADTEST_VENV}/.venv_created: requirements.txt
	python3 -m venv ${ROADTEST_VENV}
	${ROADTEST_VENV}/bin/python3 -m pip install -r requirements.txt
	touch $@
test: ${ROADTEST_VENV}/.venv_created

ifneq ($(KBUILD),0)
# Calling make on the kernel is slow even if there is nothing to be rebuilt.
# Allow the user to avoid it with KBUILD=0
${ROADTEST_BUILD_DIR}/backend.o: build-kernel
${ROADTEST_BUILD_DIR}/libvhost-user.o: build-kernel
test: build-kernel
endif

build-kernel:
	mkdir -p ${ROADTEST_BUILD_DIR}
ifneq ($(RECONFIG), 0)
	find ${ROADTEST_DIR}/roadtest/tests/ -type f -name config | xargs cat > ${ROADTEST_BUILD_DIR}/.config
ifneq ($(COV), 0)
	echo CONFIG_GCOV_PROFILE_ALL=y >> ${ROADTEST_BUILD_DIR}/.config
endif
# All config files should end with lines.  If they don't
# the grep below will fail.
	echo CONFIG_END_LINE_TEST_ONLY=y >> ${ROADTEST_BUILD_DIR}/.config
	! grep CONFIG.*CONFIG ${ROADTEST_BUILD_DIR}/.config
	${MAKE} -C ${KSOURCE} ARCH=um O=${ROADTEST_BUILD_DIR} olddefconfig
endif
	${MAKE} -C ${KSOURCE} ARCH=um O=${ROADTEST_BUILD_DIR} all compile_commands.json
	${MAKE} -C ${KSOURCE} O=${ROADTEST_BUILD_DIR} INSTALL_HDR_PATH=${KHEADERS} headers_install
	${MAKE} -C ${KSOURCE} ARCH=um O=${ROADTEST_BUILD_DIR} INSTALL_MOD_PATH=${KMODULES} modules_install

test: ${ROADTEST_BUILD_DIR}/roadtest-backend
	${ROADTEST_VENV}/bin/python3 -m pytest ${OPTS}
	#python3 -m roadtest.cmd.main --ksrc-dir ${KSOURCE} --build-dir ${ROADTEST_BUILD_DIR} --work-dir ${ROADTEST_BUILD_DIR}/roadtest-work/ ${OPTS}

# Convenient target to use with "make mypy test" to run the static checks (only,
# not style etc) before running tests.
mypy: ${ROADTEST_VENV}/.venv_created
	${ROADTEST_VENV}/bin/mypy --no-error-summary --show-error-context roadtest

check-pyflakes: ${ROADTEST_VENV}/.venv_created
	${ROADTEST_VENV}/bin/pyflakes roadtest

check-black: ${ROADTEST_VENV}/.venv_created
	${ROADTEST_VENV}/bin/black --check roadtest

check-isort: ${ROADTEST_VENV}/.venv_created
	${ROADTEST_VENV}/bin/isort --profile black --check roadtest

check-configsort:
	for f in $$(find ${ROADTEST_DIR}/roadtest/tests/ -type f -name config); do \
		LC_ALL=C sort --check --dictionary-order $$f; \
	done

configsort:
	for f in $$(find ${ROADTEST_DIR}/roadtest/tests/ -type f -name config); do \
		LC_ALL=C sort --dictionary-order --output=$$f $$f; \
	done

.PHONY: mypy check-pyflakes check-black check-isort check-configsort configsort

check: ${ROADTEST_VENV}/.venv_created mypy check-pyflakes check-black check-isort check-configsort

fmt: ${ROADTEST_VENV}/.venv_created configsort
	${ROADTEST_VENV}/bin/autoflake --in-place --recursive --imports=roadtest roadtest
	${ROADTEST_VENV}/bin/isort --profile black roadtest
	${ROADTEST_VENV}/bin/black roadtest
