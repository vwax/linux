========
Roadtest
========

Roadtest is a device-driver testing framework.  It tests drivers under User
Mode Linux using models of the hardware.  The tests cases and hardware models
are written in Python, the former using the built-in unittest framework.

Roadtest is meant to be used for relatively simple drivers, such as the ones
part of the IIO, regulator or RTC subsystems.

Drivers are tested via their userspace interfaces and interact with hardware
models which allow tests to inject values into registers and assert that
drivers control the hardware in the right way and react as expected to stimuli.

Installing the requirements
===========================

Addition to the normal requirements for building kernels, *running* roadtest
requires Python 3.9 or later, including the development libraries:

.. code-block:: shell

  apt-get -y install python3.9 libpython3.9-dev device-tree-compiler

There is also support for running the tests in a Docker container without
having to install any packages.

Running roadtest
================

To run the tests, run the following command from the base of a kernel source
tree:

.. code-block:: shell

  $ make -C tools/testing/roadtest

Or, if you prefer to use the Docker container:

.. code-block:: shell

  $ make -C tools/testing/roadtest DOCKER=1

Either of these commands will build a kernel and run all roadtests.

.. note::

  Roadtest builds the kernel out-of-tree.  The kernel build system may instruct
  you to clean your tree if you have previously performed an in-tree build.  You
  can pass the usual ``-jNN`` options to parallelize the build.  The tests
  themselves are currently always run sequentially.

Writing roadtests
=================

Tutorial: Writing your first roadtest
-------------------------------------

You may find it simplest to have a look at the existing tests and base your new
tests on them, but if you prefer, this section provides a tutorial which will
guide you to write a new basic test from scratch.

Even if you're not too keen on following the tutorial hands-on, you're
encouraged to skim through it since there are useful debugging tips and notes
on roadtest's internals which could be useful to know before diving in and
writing tests.

A quick note on the terminology before we begin: we'll refer to the framework
itself as "roadtest" or just "the framework", and we'll call a driver test
which uses this framework a "roadtest" or just a "test".

Goal for the test
~~~~~~~~~~~~~~~~~

In this tutorial, we'll add a basic test for one of the features of the
VCNL4000 light sensor driver which is a part of the IIO subsystem
(``drivers/iio/light/vcnl4000.c``).

This driver supports a bunch of related proximity and ambient light sensor
chips which communicate using the I2C protocol; we'll be testing the VCNL4000
variant.  The datasheet for the chip is, at the time of writing, available
`here <https://cdn-shop.adafruit.com/datasheets/vcnl4000.pdf>`_.

The test will check that the driver correctly reads and reports the illuminance
values from the hardware to userspace via the IIO framework.

Test file placement
~~~~~~~~~~~~~~~~~~~

Roadtests are placed under ``tools/testing/roadtest/roadtest/tests``.  (In case
you're wondering, the second ``roadtest`` is to create a Python package, so
that imports of ``roadtest`` work without having to mess with module search
paths.)

Tests are organized by subsystem.  Normally we'd put our IIO light sensor tests
under ``iio/light/`` (below the ``tests`` directory), but since there is
already a VCNL4000 test there, we'll create a new subsystem directory called
``tutorial`` and put our test there in a new file called ``test_tutorial.py``.

We'll also need to create an empty ``__init__.py`` in that directory to allow
Python to recognize it as a package.

All the commands in this tutorial should be executed from the
``tools/testing/roadtest`` directory inside the kernel source tree.  (To reduce
noise, we won't show the current working directory before the ``$`` in future
command line examples.)

.. code-block:: shell

  tools/testing/roadtest$ mkdir -p roadtest/tests/tutorial/
  tools/testing/roadtest$ touch roadtest/tests/tutorial/__init__.py

Building the module
~~~~~~~~~~~~~~~~~~~

First, we'll need to ensure that our driver is built.  To do that, we'll add
the appropriate config option to built our driver as a module.  The lines
should be written to a new file called ``config`` in the ``tutorial``
directory.  Roadtest will gather all ``config`` files placed anywhere under
``tests`` and build a kernel with the combined config.

.. code-block:: shell

   $ echo CONFIG_VCNL4000=m >> roadtest/tests/tutorial/config

.. note::

  This driver will actually be built even if you don't add this config, since
  it's already present in the ``roadtest/tests/iio/light/config`` used by the
  existing VCNL4000 test.  Roadtest uses a single build for all tests.

Loading the module from the test
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

We've set up our module to be built, so we can now start working on the test
case iself.  We'll start with the following few lines of code.  Tests are
written Python's built-in `unittest
<https://docs.python.org/3/library/unittest.html>`_ module.  This tutorial will
assume familiariy with that framework; see the Python documentation for more
information.

Test classes should subclass ``roadtest.core.suite.UMLTestCase`` instead of
``unittest.TestCase``.  This informs the roadtest core code that the test
should be run inside UML.

.. note::

  There are several "real" unit tests for the framework itself; these subclass
  ``unittest.TestCase`` directly and are run on the host system.  You'll see
  these run in the beginning when you run roadtest.

All this test currently does is insert our driver's module, do nothing, and
then remove our driver's kernel module.  (The ``roadtest.core.modules.Module``
class implements a ``ContextManager`` which automatically cleans up using the
``with`` statement.)

.. code-block:: python

  from roadtest.core.suite import UMLTestCase
  from roadtest.core.modules import Module

  class TestTutorial(UMLTestCase):
    def test_illuminance(self) -> None:
      with Module("vcnl4000"):
        pass

You can now build the kernel and run roadtest with:

.. code-block:: shell

  $ make

.. note::

  Make sure you have all the dependencies described at the beginning of the
  document installed.  You can also use a Docker container, append ``DOCKER=1``
  to all the ``make`` commands in this tutorial if you want to do that.

You should see your new test run and pass in the output of the above command:

.. code-block::

  ...
  test_illuminance (tests.tutorial.test_tutorial.TestTutorial) ... ok
  ...

Shortening feedback loops
~~~~~~~~~~~~~~~~~~~~~~~~~

While just running ``make`` runs your new test, it also runs all the *other*
tests too, and what's more, it calls in to the kernel build system every time,
and that can be relatively slow even if there's nothing to be rebuilt.

When you're only working on writing tests, and not modifying the driver or the
kernel source, you can avoid calling into Kbuild by passing ``KBUILD=0`` to the
``make`` invocation.  For example:

.. code-block:: shell

  $ make KBUILD=0

To only run specific tests, you can use the ``--filter`` option to roadtest's
main script (implemented in ``roadtest.cmd.main``) which takes a wildcard
pattern.  Only tests whoses names match the pattern are run.

Options to the main script are passed via the ``OPTS`` variable.  So the
following would both skip the kernel build and only run your test:

.. code-block:: shell

  $ make KBUILD=0 OPTS="--filter tutorial"

.. tip::

  Roadtest builds the kernel inside a directory called ``.roadtest`` in your
  kernel source tree.  Logs from UML are saved as
  ``.roadtest/roadtest-work/uml.txt`` and logs from roadtest's backend (more on
  that later) are at ``.roadtest/roadtest-work/backend.txt``.  It's sometimes
  useful to keep a terminal open running ``tail -f`` on these files while
  developing roadtests.

Adding a device
~~~~~~~~~~~~~~~

Our basic test only loads and unloads the module, so the next step is to
actually get our driver to probe and bind to a device.  On many systems,
devices are instantiated based on the hardware descriptions in devicetree, and
this is the case on roadtest's UML-based system too.  See
:ref:`Documentation/driver-api/driver-model/binding.rst <binding>` and
:ref:`Documentation/devicetree/usage-model.rst <usage-model>` for more
information.

When working on real harwdare, the hardware design specifies at what address
and on which I2C bus the hardware sensor chip is connected.  Roadtest provides
a virtual I2C bus and the test can chose to place devices at any valid address
on this bus.

In this tutorial, we'll use a hard coded device address of ``0x42`` and set the
``run_separately`` flag on the test, asking roadtest to run our test in a
separate UML instance so that we know that no other test has tried to put a
device at that I2C address.

.. note::

  Normally, roadtests use what the framework refers to as *relocatable
  devicetree fragments* (unrelated to the fragments used in devicetree
  overlays).  These do not use fixed addreses for specific devices, but instead
  allow the framework to freely assign addresses.  This allows several
  different, independent tests can be run using one devicetree and one UML
  instance (to save on startup time costs), without having to coordinate
  selection of device addesses.

  When writing "real" roadtests (after you're done with this tutorial), you too
  should use relocatable fragments.  See the existing tests for examples.

The framework's devicetree module (``roadtest.core.devicetree``) includes a
base tree that provides an I2C controller node (appropriately named ``i2c``)
for the virtual I2C, so we will add our new device under that node.

Unlike on a default Linux system, just adding the node to the devicetree won't
get our I2C driver to automatically bind to the driver when we load the module.
This is because roadtest's ``init.sh`` (a script which runs inside UML after
the kernel boots up) turns off automatic probing on the I2C bus, in order to
give the test cases full control of when things get probed.

So we'll have ask the ``test_illuminance()`` method to get the ``vcnl4000``
driver (that's the name of the I2C driver which the module registers, and
that's not necessarily the same as the name of the module) to explicitly bind
to our chosen ``0x42`` I2C device using some of the helper classes in the
framework:

.. code-block:: python

  from roadtest.core.devicetree import DtFragment
  from roadtest.core.devices import I2CDriver

  class TestTutorial(UMLTestCase):
    run_separately = True
    dts = DtFragment(
      src="""
  &i2c {
      light-sensor@42 {
          compatible = "vishay,vcnl4000";
          reg = <0x42>;
      };
  };
      """,
    )

    def test_illuminance(self) -> None:
      with (
        Module("vcnl4000"),
        I2CDriver("vcnl4000").bind(0x42) as dev,
      ):
        pass

You can run this test using the same ``make`` command you used previously.
This time, rather than an "ok", you should see roadtest complain about an error
during your test:

.. code-block::

  ======================================================================
  ERROR: test_illuminance (tests.tutorial.test_tutorial.TestTutorial)
  ----------------------------------------------------------------------
  Backend log:
    Traceback (most recent call last):
      File ".../roadtest/backend/i2c.py", line 35, in write
        raise Exception("No I2C model loaded")
    Exception: No I2C model loaded
    Traceback (most recent call last):
      File ".../roadtest/backend/i2c.py", line 29, in read
        raise Exception("No I2C model loaded")
    Exception: No I2C model loaded

  UML log:
    [ 1220.410000][   T19] vcnl4000: probe of 0-0042 failed with error -5

  Traceback (most recent call last):
    File ".../roadtest/tests/tutorial/test_tutorial.py", line 21, in test_illuminance
      with (
    File "/usr/lib/python3.9/contextlib.py", line 119, in __enter__
      return next(self.gen)
    File ".../roadtest/core/devices.py", line 32, in bind
      f.write(dev.id.encode())
  OSError: [Errno 5] Input/output error

To understand and fix this error, we'll have to learn a bit about how roadtest
works under the hood.

Adding a hardware model
~~~~~~~~~~~~~~~~~~~~~~~

Roadtest's *backend* is what allows the hardware to modelled for the sake of
driver testing.  The backend runs outside of UML and communication between the
drivers and the models goes via ``virtio-uml``, a shared-memory based
communication protocol.  At its lowest level, the backend is written in C and
implements virtio devices for ``virtio-i2c`` and ``virtio-gpio``, both of which
have respective virtio drivers which run inside UML and provide the virtual I2C
bus (and GPIO controller) whose nodes are available in the devicetree.

The C backend embeds a Python interpreter which runs a Python module which
implements the I2C bus model.  It's that Python module which is complaining now
that it does not have any I2C device model to handle the I2C transactions that
it received from UML.  This is quite understandable since we haven't
implemented one yet!

.. note::

  In the error message above, you'll also notice an error ``printk()`` from the
  driver (as part of the *UML log*, which includes kernel console messages), as
  well as the exception stacktrace from the test case itself.  The ``-EIO``
  seen inside UML is a result of the roadtest backend failing the I2C
  transaction due to the exception.

Models are placed in the same source file as the test cases.  The model and
the test cases will however run in two different Python interpreters on two
different systems (the test case inside UML, and the model inside the backend
on your host).

For I2C, the interface our model needs to implement is specified by the
Abstract Base Class ``roadtest.backend.i2c.I2CModel`` (which can be found,
following Python's standard naming conventions, in the file
``roadtest/backend/i2c.py``).  You can see that it expects the model to
implement ``read()`` and ``write()`` functions which transmit and receive the
raw bytes of the I2C transaction.

Our VCNL4000 device uses the SMBus protocol which is a subset of the I2C
protocol, so we can use a higher-level class to base our implementation off,
``roadtest.backend.i2c.SMBusModel``.  This one takes care of doing segmentation
of the I2C requests, and expects subclasses to implement ``reg_read()`` and
``reg_write()`` methods which will handle the register access for the device.

For our initial model, we'll just going to just make our ``reg_read()`` and
``reg_write()`` methods read and store the register values in a dictionary.
We'll need some initial values for the registers, and for these we use the
values which are specified in the VCNL4000's datasheet.  We won't bother with
creating constants for the register addresses and we'll just specify them in
hex:

.. code-block:: python

  from typing import Any
  from roadtest.backend.i2c import SMBusModel

  class VCNL4000(SMBusModel):
      def __init__(self, **kwargs: Any) -> None:
          super().__init__(regbytes=1, **kwargs)
          self.regs = {
              0x80: 0b_1000_0000,
              0x81: 0x11,
              0x82: 0x00,
              0x83: 0x00,
              0x84: 0x00,
              0x85: 0x00,
              0x86: 0x00,
              0x87: 0x00,
              0x88: 0x00,
              0x89: 0x00,
          }

      def reg_read(self, addr: int) -> int:
          val = self.regs[addr]
          return val

      def reg_write(self, addr: int, val: int) -> None:
          assert addr in self.regs
          self.regs[addr] = val

Then we need to modify the test function to ask the backend to load this model:

.. code-block:: python
  :emphasize-lines: 1,6

  from roadtest.core.hardware import Hardware

  def test_illuminance(self) -> None:
    with (
      Module("vcnl4000"),
      Hardware("i2c").load_model(VCNL4000),
      I2CDriver("vcnl4000").bind(0x42),
    ):
      pass

Now run the test again.  You should see the test pass, meaning that the driver
successfully talked to and recognized your hardware model.  (You can look at
the UML and backend logs mentioned earlier to confirm this.)

.. tip::

  You can add arbitrary command line arguments to UML using the
  ``--uml-append`` option.  For example, while developing tests for I2C
  drivers, it could be helpful to turn on the appropriate trace events and
  arrange for them to be printed to the console (which you can then access via
  the previously mentioned ``uml.txt``.):

  .. code-block::

    OPTS="--filter tutorial --uml-append tp_printk trace_event=i2c:*"

Exploring the target
~~~~~~~~~~~~~~~~~~~~

Now that we've gotten the driver to probe to our new device, we want to get the
test to read the illuminance value from the driver.  However, which file should
the test read the value from?  IIO exposes the illuminance value in a sysfs
file, but where do we find this file?

If you have real hardware with a VCNL4000 chip and already running the vcnl4000
driver, or are already very familiar with the IIO framework, you likely already
know what sysfs files to read, but in our case, we can open up a shell on UML
to manually explore the system and find the relevant sysfs files before
implementing the rest of the test case.

Roadtest's ``--shell`` option makes UML start a shell instead of exiting after
the tests are run.  However, since our test case cleans up after itself (as
it should) using context managers, neither the module nor the model would
remain loaded after the test exists, which would make manual exploration
difficult.

To remedy this, we can combine ``--shell`` with temporary code in our test to
_exit(2) after setting up everything:

.. code-block:: python
  :emphasize-lines: 5,7

  def test_illuminance(self) -> None:
    with (
      Module("vcnl4000"),
      Hardware("i2c").load_model(VCNL4000),
      I2CDriver("vcnl4000").bind(0x42) as dev,
    ):
      print(dev.path)
      import os; os._exit(1)

.. note::

  The communication between the test cases and the models uses a simple text
  based protocol where the test cases write Python expressions to a file which
  the backend reads and evaluates, so it is possible to load a model using only
  shell commands, but this is undocumented.  See the source code if you need to
  do this.

We'll also need to ask UML to open up a terminal emulator (``con=xterm``) or start a telnet server
and wait for a connection (``con=port:9000``).  See
:ref:`Documentation/virt/uml/user_mode_linux_hotwo_v2.rst
<user_mode_linux_hotwo_v2>` for more information about the required packages.
These options can be passed to UML using ``--uml-append``.  So the final
``OPTS`` argument is something like the following (you can combine this with
the tracing options):

.. code-block::

  OPTS="--shell --uml-append con=xterm"

.. tip::

  ``con=xterm doesn``'t work in the Docker container, so use the telnet option
  if you're running roadtest inside Docker.  ``screen -L //telnet localhost
  9000`` or similar can be used to connect to UML.

  When running *without* using Docker, the telnet option tends to leave UML's
  ``port-helper`` running in the background, so you may have to ``kill(1)`` it
  yourself after each run.

Using the shell, you should be able to find the illuminance file under the
device's sysfs path:

.. code-block::

  root@(none):/sys/bus/i2c/devices/0-0042# ls -1 iio\:device0/in*
  iio:device0/in_illuminance_raw
  iio:device0/in_illuminance_scale
  iio:device0/in_proximity_nearlevel
  iio:device0/in_proximity_raw

You can also attempt to read the ``in_illuminance_raw`` file; you should see
that it fails with something like this (with the trace events enabled):

.. code-block::

  root@(none):/sys/bus/i2c/devices/0-0042# cat iio:device0/in_illuminance_raw
  [  151.270000][   T34] i2c_write: i2c-0 #0 a=042 f=0000 l=2 [80-10]
  [  151.270000][   T34] i2c_result: i2c-0 n=1 ret=1
  ...
  [  152.030000][   T34] i2c_write: i2c-0 #0 a=042 f=0000 l=1 [80]
  [  152.030000][   T34] i2c_read: i2c-0 #1 a=042 f=0001 l=1
  [  152.030000][   T34] i2c_reply: i2c-0 #1 a=042 f=0001 l=1 [10]
  [  152.030000][   T34] i2c_result: i2c-0 n=2 ret=2
  [  152.070000][   T34] vcnl4000 0-0042: vcnl4000_measure() failed, data not ready

Controlling register values
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Our next challenge is to get the ``in_illuminance_raw`` file to be read
successfully.  From the I2C trace events above, or from looking at the
``backend.txt`` (below), we can see that the driver repeatedly reads a
particular register.

.. code-block::

  INFO - roadtest.core.control: START<roadtest.tests.tutorial.test_tutorial.TestTutorial.test_illuminance>
  DEBUG - roadtest.core.control: backend.i2c.load_model(*('roadtest.tests.tutorial.test_tutorial', 'VCNL4000'), **{})
  DEBUG - roadtest.backend.i2c: SMBus read addr=0x81 val=0x11
  DEBUG - roadtest.backend.i2c: SMBus write addr=0x80 val=0x10
  DEBUG - roadtest.backend.i2c: SMBus read addr=0x80 val=0x10
  DEBUG - roadtest.backend.i2c: SMBus read addr=0x80 val=0x10
  ...

To understand this register, we need to take a look at the chip's datasheet and
compare it with the driver code.  By doing so, we can see the driver is waiting
for the hardware to signal that the data is ready by polling for a particular
bit to be set.

One simple way to set the data ready bit, which we'll use for the purpose of
this tutorial, is to simply ensure that the model always returns reads to the
0x80 register with that bit set.

.. note::

  This method wouldn't allow a test to be written to test the timeout handling,
  but we won't bother with that in this tutorial.  You can explore the exising
  roadtests for alternative solutions, such as setting the data ready bit
  whenever the test injects new data and clearing it when the driver reads the
  data.

.. code-block:: python
  :emphasize-lines: 4,5

  def reg_read(self, addr: int) -> int:
    val = self.regs[addr]

    if addr == 0x80:
      val |= 1 << 6

    return val

This should get the bit set and make the read succeed (you can check this using
the shell), but we'd also like to return different values from the data
registers rather the reset values we hardcoded in ``__init__``.  One way to do
this is to have the test inject the values into the ALS result registers by
having it call the ``reg_write()`` method of the model.  It can do this via the
``Hardware`` object.

.. note::

  The test can call methods on the model but it can't receive return values
  from these methods, nor can it set attributes on the model.  The model and
  the test run on different systems and communication between them is
  asynchronous.

We'll combine this with a read of the sysfs file we identified and throw in an
assertion to check that the value which the driver reports to userspace via
that file matches the value which we inject into the hardware's result
registers:

.. code-block:: python
   :emphasize-lines: 6,8,9-13

    from roadtest.core.sysfs import read_int

    def test_illuminance(self) -> None:
        with (
            Module("vcnl4000"),
            Hardware("i2c").load_model(VCNL4000) as hw,
            I2CDriver("vcnl4000").bind(0x42) as dev,
        ):
            hw.reg_write(0x85, 0x12)
            hw.reg_write(0x86, 0x34)
            self.assertEqual(
                read_int(dev.path / "iio:device0/in_illuminance_raw", 0x1234)
            )

And that's it for this tutorial.  We've written a simple end-to-end test for
one aspect of this driver with the help of a minimal model of the hardware.

Verifying drivers' interactions with the hardware
-------------------------------------------------

The tutorial covered injection of values into hardware registers and how to
check that the driver interprets the value exposed by the hardware correctly,
but another important aspect of testing device drivers is to verify that the
driver actually *controls* the hardware in the expected way.

For example, if you are testing a regulator driver, you want to test that
driver actually writes the correct voltage register in the hardware with the
correct value when the driver is asked to set a voltage using the kernel's
regulator API.

To support this, roadtest integrates with Python's built-in `unittest.mock
<https://docs.python.org/3/library/unittest.mock.html>`_ library.  The
``update_mock()`` method on the ``Hardware`` objects results in a ``HwMock`` (a
subclass of ``unittest.mock``'s ``MagicMock``) object which, in the case of
``SMBusModel``, provides access to a log of all register writes and their
values.

The object can be then used to check which registers the hardware has written
with which values, and to assert that the expect actions have been taken.

See ``roadtest/tests/regulator/test_tps62864.py`` for an example of this.

GPIOs
-----

The framework includes support for hardware models to trigger interrupts by
controlling GPIOs.  See ``roadtest/tests/rtc/test_pcf8563.py`` for an example.

Support has not been implemented yet for asserting that drivers control GPIOs
correctly.  See the comment in ``gpio_handle_cmdq()`` in ``src/backend.c``.

Coding guidelines
-----------------

Run ``make fmt`` to automatically format your Python code to follow the coding
style.  Run ``make check`` and ensure that your code passes static checkers and
style checks.  Typing hints are mandatory.

These two commands require that you have installed the packages listed in
``requirements.txt``, for example with something like the following patch and
then ensuring that ``~/.local/bin`` is in your ``$PATH``.

.. code-block:: shell

  $ pip3 install --user -r requirements.txt

Alternatively, you can also run these commands in the Docker container (by
appending ``DOCKER=1`` to the ``make`` commands) which has all the correct
tools installed.
