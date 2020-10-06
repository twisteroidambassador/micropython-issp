"""Tools for converting official vectors to use in issp.py"""

import enum


class ISSPOp(enum.Enum):
    WRITE_MEM = '100'
    READ_MEM = '101'
    WRITE_REG = '110'
    READ_REG = '111'
    NO_OP = '000'


def parse(commands_str: str):
    """Parse the official vectors presented in the ISSP Programming Specification document.

    Each command, represented by 22 binary bits, is converted to a tuple, either (NO_OP,) or (op, address, value).
    `op` is a member of ISSPOp. `address` and `value` are kept as strings.
    Returns a list of command tuples.
    """
    commands_str = ''.join((c if c not in ('\r', '\n', ' ', '\t') else '') for c in commands_str)
    commands = []
    for p in range(0, len(commands_str), 22):
        single_command_str = commands_str[p : p+22]
        op = ISSPOp(single_command_str[0:3])
        if op is ISSPOp.NO_OP:
            commands.append((op,))
            continue
        address = single_command_str[3:11]
        if op in (ISSPOp.WRITE_MEM, ISSPOp.WRITE_REG):
            value = single_command_str[11:19]
        else:
            value = single_command_str[12:20]
        commands.append((op, address, value))
    return commands


def generate_code(commands):
    """Print commands returned from parse() as pseudocode."""
    for command in commands:
        if command[0] is ISSPOp.NO_OP:
            print('write_noop()')
            continue
        op, address, value = command
        try:
            address = int(address, base=2)
            address = '0x{:02X}'.format(address)
        except ValueError:
            pass
        try:
            value = int(value, base=2)
            value = '0x{:02X}'.format(value)
        except ValueError:
            pass
        if op is ISSPOp.WRITE_REG:
            print(f'write_register({address}, {value})')
        elif op is ISSPOp.WRITE_MEM:
            print(f'write_memory({address}, {value})')
        elif op is ISSPOp.READ_REG:
            print(f'read_register({address})')
        elif op is ISSPOp.READ_MEM:
            print(f'read_memory({address})')


def generate_bytes(commands):
    """Generate VECTORs from commands returned from parse().

    VECTORs are bytes objects. NO_OP is represented by a single zero byte. READ_MEM and READ_REG are each represented
    by 3 bytes (op, address, value).
    """
    out_bytes = []
    for command in commands:
        if command[0] is ISSPOp.NO_OP:
            out_bytes.append(0)
        else:
            out_bytes.append(int(command[0].value, base=2))
            out_bytes.extend(int(c, base=2) for c in command[1:])
    return bytes(out_bytes)


def g(commands_str):
    generate_code(parse(commands_str))


def b(command_str):
    return generate_bytes(parse(command_str))
