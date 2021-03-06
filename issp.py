"""ISSP protocol for MicroPython

This module implements parts of the ISSP protocol, used to program Cypress PSoC1 devices.
It is intended to be run interactively on a PyBoard v1.1 via its USB serial REPL.

Before using this module, edit the values below in the "configuration options" section to match the actual
hardware you're using.

The accompanying intelhex.py file is a tool to convert .hex files generated by PSoC Designer to binary formats
used by this module.


Copyright (C) 2020  twisteroid ambassador

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.


References:
CY8C21x45, CY8C22x45, CY8C24x94, CY8C28xxx, CY8C29x66, CY8CTST120, CY8CTMA120, CY8CTMG120, CY7C64215
PSoC ® 1 ISSP Programming Specifications
Document No. 001-15239 Rev. *L
October 5, 2015
https://www.cypress.com/file/42201

https://syscall.eu/blog/2018/03/12/aigo_part2/
"""

import gc
import machine
import micropython
import pyb

from micropython import const

# ========== configuration options ==========
sdata = pyb.Pin('X7')
sclk = pyb.Pin('X8')
xres = pyb.Pin('Y12')

"""The timer is used to generate a clock pulse for wait-and-poll."""
timer = pyb.Timer(7)

"""If target is powered by 5V, set to True. If target is powered by 3.3V, set to False."""
is_5v = True

"""A machine.Signal that controls the power to the target. If your board does not control target's power,
set to None. Only used by the various power-related methods."""
power_enable = machine.Signal('X6', machine.Pin.OUT, None, invert=False)
# ========== configuration options ==========

_ISSP_OP_WRITE_MEM = const(4)
_ISSP_OP_READ_MEM = const(5)
_ISSP_OP_WRITE_REG = const(6)
_ISSP_OP_READ_REG = const(7)

_WAIT_AND_POLL_TIMEOUT_US = const(100000)

_BYTE_PER_BLOCK = const(64)
_BLOCK_PER_BANK = const(128)


# _VECTOR_* are translated from the official PSOC1 ISSP Programming Specifications document.
# See issp_parser.py for details.
_VECTOR_INIT_1 = (
    b'\x00\x00\x00\x00\x00\x06\xf7\x00\x06\xf6\x00\x04\xf8:\x04\xf9\x03'
    b'\x06\xf5\x00\x06\xf4\x03\x04\xfb\x80\x06\xf90\x06\xfa@\x06\xf0\t\x06\xf8\x00\x06\xff\x12'
)

_VECTOR_INIT_2 = (
    b'\x06\xf7\x00\x06\xf6\x00\x04\xf8:\x04\xf9\x03\x06\xf5\x00\x06\xf4\x03'
    b'\x04\xfb\x80\x06\xf90\x06\xfa@\x04\xfa\x01\x06\xf0\x06\x06\xf8\x00\x06\xff\x12'
)

_VECTOR_INIT_3_3V = (
    b'\x06\xf7\x00\x06\xf4\x03\x06\xf5\x00\x06\xf6\x08\x06\xf8Q\x06\xf9\xf8'
    b'\x06\xfa0\x06\xff\x12\x00\x06\xf7\x00\x06\xf4\x03\x06\xf5\x00\x06\xf6\x08'
    b'\x06\xf8`\x06\xf9\xea\x06\xfa0\x06\xf7\x10\x06\xff\x12\x00\x06\xf7\x00'
    b'\x06\xf4\x03\x06\xf5\x00\x06\xf6\x08\x06\xf8Q\x06\xf9\xf9\x06\xfa0'
    b'\x06\xff\x12\x00\x06\xf7\x00\x06\xf4\x03\x06\xf5\x00\x06\xf6\x08'
    b'\x06\xf8`\x06\xf9\xe8\x06\xfa0\x06\xf7\x10\x06\xff\x12\x00'
)

_VECTOR_INIT_3_5V = (
    b'\x06\xf7\x00\x06\xf4\x03\x06\xf5\x00\x06\xf6\x08\x06\xf8Q\x06\xf9\xfc'
    b'\x06\xfa0\x06\xff\x12\x00\x06\xf7\x00\x06\xf4\x03\x06\xf5\x00\x06\xf6\x08'
    b'\x06\xf8`\x06\xf9\xea\x06\xfa0\x06\xf7\x10\x06\xff\x12\x00\x06\xf7\x00'
    b'\x06\xf4\x03\x06\xf5\x00\x06\xf6\x08\x06\xf8Q\x06\xf9\xfd\x06\xfa0'
    b'\x06\xff\x12\x00\x06\xf7\x00\x06\xf4\x03\x06\xf5\x00\x06\xf6\x08'
    b'\x06\xf8`\x06\xf9\xe8\x06\xfa0\x06\xf7\x10\x06\xff\x12\x00'
)

_VECTOR_ID_SETUP = (
    b'\x06\xf7\x10\x06\xe0\x02\x06\xf7\x00\x06\xf6\x00\x04\xf8:\x04\xf9\x03'
    b'\x06\xf5\x00\x06\xf4\x03\x04\xfb\x80\x06\xf90\x06\xfa@\x04\xfa\x00'
    b'\x06\xf0\x06\x06\xf8\x00\x06\xff\x12'
)

_VECTOR_BULK_ERASE = (
    b'\x04\xfc\x15\x04\xfeV\x06\xf7\x00\x06\xf6\x00\x04\xf8:\x04\xf9\x03\x06\xf5\x00'
    b'\x06\xf4\x03\x04\xfb\x80\x06\xf90\x06\xfa@\x06\xf0\x05\x06\xf8\x00\x06\xff\x12'
)

_VECTOR_PROGRAM_BLOCK = (
    b'\x04\xfcT\x04\xfeV\x06\xf7\x00\x06\xf6\x00\x04\xf8:\x04\xf9\x03\x06\xf5\x00'
    b'\x06\xf4\x03\x04\xfb\x80\x06\xf90\x06\xfa@\x06\xf0\x02\x06\xf8\x00\x06\xff\x12'
)

_VECTOR_VERIFY_SETUP = (
    b'\x06\xf7\x00\x06\xf6\x00\x04\xf8:\x04\xf9\x03\x06\xf5\x00\x06\xf4\x03\x04\xfb\x80'
    b'\x06\xf90\x06\xfa@\x06\xf0\x01\x06\xf8\x00\x06\xff\x12'
)

_VECTOR_ERASE_BLOCK = (
    b'\x04\xfcT\x04\xfeV\x06\xf7\x00\x06\xf6\x00\x04\xf8:\x04\xf9\x03\x06\xf5\x00'
    b'\x06\xf4\x03\x06\xf90\x06\xfa@\x06\xf0\x03\x06\xf8\x00\x06\xff\x12'
)


def init_pins():
    """Initialize all pins to output mode.

    Most other methods in this module expect the pins to be initialized this way.
    """
    sdata.init(pyb.Pin.OUT_PP, pyb.Pin.PULL_NONE)
    sclk.init(pyb.Pin.OUT_PP, pyb.Pin.PULL_NONE)
    xres.init(pyb.Pin.OUT_PP, pyb.Pin.PULL_NONE)


def deinit_pins():
    """Put all pins into high-Z mode."""
    sdata.init(pyb.Pin.IN, pyb.Pin.PULL_NONE)
    sclk.init(pyb.Pin.IN, pyb.Pin.PULL_NONE)
    xres.init(pyb.Pin.IN, pyb.Pin.PULL_NONE)


def power_on():
    """Turn on power to the target.

    The signal pins are put into high-Z mode to prevent back feeding.
    """
    deinit_pins()
    power_enable.on()
    pyb.udelay(100)


def power_off():
    """Turn off power to the target.

    The signal pins are put into high-Z mode to prevent back feeding.
    """
    deinit_pins()
    power_enable.off()


@micropython.viper
def _drive_clock(cycles: int):
    while cycles > 0:
        sclk(1)
        sclk(0)
        cycles -= 1


@micropython.viper
def _on_callback(t):
    sclk(1)
    t.callback(_off_callback)


@micropython.viper
def _off_callback(t):
    sclk(0)
    t.deinit()


@micropython.viper
def wait_and_poll():
    """Perform a wait-and-poll.

    Uses a timer to generate the first clock cycle.
    """
    sdata.init(pyb.Pin.IN)

    timer.init(freq=50000, callback=_on_callback)

    ret = int(machine.time_pulse_us(sdata, 1, _WAIT_AND_POLL_TIMEOUT_US))
    if ret == -2:
        raise RuntimeError('Timed out waiting for SDATA to go high')
    elif ret == -1:
        raise RuntimeError('Timed out waiting for SDATA to go low')

    sdata(0)
    sdata.init(pyb.Pin.OUT_PP)
    _drive_clock(40)


@micropython.viper
def write_noop():
    """Send 22 zeros to the target."""
    sdata(0)
    _drive_clock(22)


@micropython.viper
def reset_send_magic():
    """Reset the target using XRES pin, and send the sequence to put target into ISSP mode.

    The first 22 bits of the Initialize-1 vector is sent.

    Note: this method initialize pins, and also invokes the garbage collector, before sending the magic bits.

    Timing note: The reset procedure has tight timing requirements. This method uses busy loops to generate delays.
    Verify timing with a logic analyzer and tweak as required.
    """
    init_pins()
    gc.collect()

    sdata(0)
    sclk(0)
    xres(0)
    for _ in range(100):
        pass

    xres(1)
    for _ in range(100):
        pass

    xres(0)
    for _ in range(20):
        pass

    sdata(1)
    sclk(1)
    sclk(0)

    sclk(1)
    sclk(0)

    sdata(0)
    sclk(1)
    sclk(0)

    sclk(1)
    sclk(0)

    sdata(1)
    sclk(1)
    sclk(0)

    sdata(0)
    sclk(1)
    sclk(0)

    sdata(1)
    sclk(1)
    sclk(0)

    sdata(0)
    i = 0
    while i < 15:
        sclk(1)
        sclk(0)
        i += 1


@micropython.viper
def power_cycle_send_magic():
    """Cycle the target's power and send the sequence to put target into ISSP mode.

    The first 22 bits of the Initialize-1 vector is sent.

    Note: this method initialize pins, and also invokes the garbage collector, before sending the magic bits.

    Timing note: the power cycle procedure is somewhat less strict than the XRES reset procedure.
    However, there's the risk of not catching the high-to-low transition on sdata. Try tweaking the delay after
    power_enable.on().
    """
    power_off()
    gc.collect()
    pyb.delay(100)

    xres.init(pyb.Pin.OUT_PP, pyb.Pin.PULL_NONE)
    xres(0)
    power_enable.on()
    pyb.udelay(100)
    ret = int(machine.time_pulse_us(sdata, 1, _WAIT_AND_POLL_TIMEOUT_US))
    if ret == -2:
        raise RuntimeError('Timed out waiting for SDATA to go high')
    elif ret == -1:
        raise RuntimeError('Timed out waiting for SDATA to go low')

    sdata.init(pyb.Pin.OUT_PP, pyb.Pin.PULL_NONE)
    sclk.init(pyb.Pin.OUT_PP, pyb.Pin.PULL_NONE)

    sdata(1)
    sclk(1)
    sclk(0)

    sclk(1)
    sclk(0)

    sdata(0)
    sclk(1)
    sclk(0)

    sclk(1)
    sclk(0)

    sdata(1)
    sclk(1)
    sclk(0)

    sdata(0)
    sclk(1)
    sclk(0)

    sdata(1)
    sclk(1)
    sclk(0)

    sdata(0)
    i = 0
    while i < 15:
        sclk(1)
        sclk(0)
        i += 1


@micropython.viper
def _read_op(issp_op: int, address: int) -> int:
    i = 2
    while i >= 0:
        sdata((issp_op >> i) & 1)
        sclk(1)
        sclk(0)
        i -= 1

    i = 7
    while i >= 0:
        sdata((address >> i) & 1)
        sclk(1)
        sclk(0)
        i -= 1

    read_value = 0

    sdata.init(pyb.Pin.IN)
    sclk(1)
    sclk(0)
    sclk(1)
    sclk(0)

    i = 7
    while i >= 0:
        read_value |= int(sdata()) << i
        sclk(1)
        sclk(0)
        i -= 1

    sclk(1)
    sclk(0)
    sdata.init(pyb.Pin.OUT_PP)
    return read_value


@micropython.viper
def _write_op(issp_op: int, address: int, value: int):
    i = 2
    while i >= 0:
        sdata((issp_op >> i) & 1)
        sclk(1)
        sclk(0)
        i -= 1

    i = 7
    while i >= 0:
        sdata((address >> i) & 1)
        sclk(1)
        sclk(0)
        i -= 1

    i = 7
    while i >= 0:
        sdata((value >> i) & 1)
        sclk(1)
        sclk(0)
        i -= 1

    sdata(1)
    i = 0
    while i < 3:
        sclk(1)
        sclk(0)
        i += 1


@micropython.viper
def read_memory(address: int) -> int:
    """Read a byte of memory at `address`."""
    return int(_read_op(_ISSP_OP_READ_MEM, address))


@micropython.viper
def read_register(address: int) -> int:
    """Read a byte of the register at `address`."""
    return int(_read_op(_ISSP_OP_READ_REG, address))


@micropython.viper
def write_memory(address: int, value: int):
    """Write a byte `value` to memory at `address`."""
    _write_op(_ISSP_OP_WRITE_MEM, address, value)


@micropython.viper
def write_register(address: int, value: int):
    """Write a byte `value` to register at `address`."""
    _write_op(_ISSP_OP_WRITE_REG, address, value)


@micropython.viper
def _write_vector(ops):
    ptr_ops = ptr8(ops)
    i = 0
    len_ops = int(len(ops))
    while i < len_ops:
        if ptr_ops[i] == 0:
            write_noop()
            i += 1
            continue
        assert i + 3 <= len_ops
        _write_op(ptr_ops[i], ptr_ops[i+1], ptr_ops[i+2])
        i += 3


def reset():
    """Reset the target via XRES, using the official vectors.

    This method uses the appropriate vectors depending on the value of `is_5v`. Make sure it's set correctly.
    """
    reset_send_magic()
    _write_vector(_VECTOR_INIT_1)
    wait_and_poll()
    _write_vector(_VECTOR_INIT_2)
    wait_and_poll()
    if is_5v:
        _write_vector(_VECTOR_INIT_3_5V)
    else:
        _write_vector(_VECTOR_INIT_3_3V)


def power_cycle_init():
    """Reset the target by power cycling, using the official vectors.

    This method uses the appropriate vectors depending on the value of `is_5v`. Make sure it's set correctly.
    """
    power_cycle_send_magic()
    _write_vector(_VECTOR_INIT_1)
    wait_and_poll()
    _write_vector(_VECTOR_INIT_2)
    wait_and_poll()
    if is_5v:
        _write_vector(_VECTOR_INIT_3_5V)
    else:
        _write_vector(_VECTOR_INIT_3_3V)


def read_id_word():
    """Read target's Silicon ID.

    Returns 2 ints representing the high byte and low byte of the ID word.
    """
    _write_vector(_VECTOR_ID_SETUP)
    wait_and_poll()
    high = read_memory(0xF8)
    low = read_memory(0xF9)
    return high, low


def set_bank_num(bank):
    """Set active flash bank."""
    write_register(0xF7, 0x10)
    write_register(0xFA, bank)
    write_register(0xF7, 0x00)


def set_block_num(block):
    """Set block number for the next program / erase / verify procedure."""
    write_memory(0xFA, block)


def bulk_erase():
    """Send the bulk erase vector which erases all flash memory contents and security bits."""
    _write_vector(_VECTOR_BULK_ERASE)
    wait_and_poll()


def program_block():
    """Send the program vector to program one block of flash from memory."""
    _write_vector(_VECTOR_PROGRAM_BLOCK)
    wait_and_poll()


def program(data):
    """Erase the target, then program the target with `data`, using the official procedure.

    `data` should be a bytes-like that contains the entire content of the flash memory to be programmed. Its length
    must be a multiple of 8192 bytes.

    A "+" sign is printed for each block successfully programmed.
    """
    total_banks, remainder = divmod(len(data), _BYTE_PER_BLOCK * _BLOCK_PER_BANK)
    assert remainder == 0
    print('Programming')
    bulk_erase()
    i = 0
    for i_bank in range(total_banks):
        print('Bank', i_bank, end=':')
        set_bank_num(i_bank)
        for i_block in range(_BLOCK_PER_BANK):
            for i_byte in range(_BYTE_PER_BLOCK):
                write_memory(0b10000000 | i_byte, data[i])
                i += 1
            set_block_num(i_block)
            program_block()
            print('+', end='')
        print('')
    assert i == len(data)
    print('Program done')


def verify_setup():
    """Send the verify setup vector to read one block of flash into memory."""
    _write_vector(_VECTOR_VERIFY_SETUP)
    wait_and_poll()


def verify(data):
    """Verify the target's flash memory content against `data`, using the official procedure.

    A "-" sign is printed for each block successfully verified. If the flash does not match `data`, an exception
    is raised.

    Note: this method will not work properly if any flash block is read protected, and it does not check whether
    flash is read into memory correctly.
    """
    total_banks, remainder = divmod(len(data), _BYTE_PER_BLOCK * _BLOCK_PER_BANK)
    assert remainder == 0
    print('Verifying')
    i = 0
    for i_bank in range(total_banks):
        print('Bank', i_bank, end=':')
        set_bank_num(i_bank)
        for i_block in range(_BLOCK_PER_BANK):
            set_block_num(i_block)
            verify_setup()
            for i_byte in range(_BYTE_PER_BLOCK):
                if data[i] != read_memory(0b10000000 | i_byte):
                    raise RuntimeError('Verify failed at bank {} block {} byte {}'.format(i_bank, i_block, i_byte))
                i += 1
            print('-', end='')
        print('')
    assert i == len(data)
    print('Verify done')


def erase_block():
    """Send the erase block vector to erase one flash block."""
    _write_vector(_VECTOR_ERASE_BLOCK)
    wait_and_poll()


def patch(data):
    """Make the target's flash memory contents the same as `data`, by programming blocks that are different.

    This is not an official procedure. It's useful while iterating through code versions, since there are usually
    many identical blocks between different versions of firmware.

    Each block is first read and compared to `data`. If a block is different, it is erased and programmed. A "-" sign
    is printed for each block successfully verified to be identical, and a "+" sign is printed for each block
    successfully programmed.
    """
    total_banks, remainder = divmod(len(data), _BYTE_PER_BLOCK * _BLOCK_PER_BANK)
    assert remainder == 0
    print('Patching')
    for i_bank in range(total_banks):
        print('Bank', i_bank, end=':')
        set_bank_num(i_bank)
        for i_block in range(_BLOCK_PER_BANK):
            block_begin = (i_bank * _BLOCK_PER_BANK + i_block) * _BYTE_PER_BLOCK
            set_block_num(i_block)
            verify_setup()
            return_code = read_memory(0xf8)
            if return_code != 0:
                raise RuntimeError('Reading flash failed at bank {} block {}, return code {}'.format(
                    i_bank, i_block, return_code))
            for i_byte in range(_BYTE_PER_BLOCK):
                if data[block_begin + i_byte] != read_memory(0b10000000 | i_byte):
                    break
            else:
                print('-', end='')
                continue
            set_block_num(i_block)
            erase_block()
            return_code = read_memory(0xf8)
            if return_code != 0:
                raise RuntimeError('Erasing flash failed at bank {} block {}, return code {}'.format(
                    i_bank, i_block, return_code))
            for i_byte in range(_BYTE_PER_BLOCK):
                write_memory(0b10000000 | i_byte, data[block_begin + i_byte])
            set_block_num(i_block)
            program_block()
            return_code = read_memory(0xf8)
            if return_code != 0:
                raise RuntimeError('Programming flash failed at bank {} block {}, return code {}'.format(
                    i_bank, i_block, return_code))
            print('+', end='')
        print('')
    print('Patch done')
