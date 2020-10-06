"""Convert .hex files generated by PSoC Designer into binary files, used by issp.py.

This tool is intended to be run on a computer. The converted binary files can be copied to the flash memory
of a PyBoard, and used to flash PSoC1 targets with issp.py.

This tool only supports the specific IntelHex format specified by ISSP Programming Specifications.
It expects the specific block lengths and extended addresses, and will throw exceptions if expectations are not
met. It is not a generic IntelHex parser and converter.


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

https://en.wikipedia.org/wiki/Intel_HEX
"""

import argparse
import pathlib

_BLOCK_PROGRAM_DATA = 0
_BLOCK_EOF = 1
_BLOCK_EXTENDED_LINEAR_ADDR = 4

_EXTENDED_ADDRESS_SECURITY = 0x0010
_EXTENDED_ADDRESS_CHECKSUM = 0x0020

BLOCKS_PER_BANK = 128


def read_hex_file(hexfile):
    """Read and parse a PSoC1 IntelHex file.

    `hexfile` should be a file object opened for reading in text mode.

    Returns (program_data, security_data, checksum). Each element is a bytes object, consisting of all the respective
    data from the original hex file concatenated together.
    """
    blocks = []
    security = []
    device_checksum = None
    extended_address = 0
    next_block_num = 0
    num_banks = None  # set this to actual number of banks after all blocks are read
    for line in hexfile:
        if not line.startswith(':'):
            continue
        # line_bytes = binascii.unhexlify(line[1:].strip())
        line_bytes = bytes.fromhex(line[1:].strip())
        if sum(line_bytes) % 256:
            raise ValueError('Incorrect checksum')
        block_len = line_bytes[0]
        address = int.from_bytes(line_bytes[1:3], 'big')
        record_type = line_bytes[3]
        block_data = line_bytes[4:-1]
        if block_len != len(block_data):
            raise ValueError('Incorrect data length')

        if record_type == _BLOCK_EOF:
            break
        elif record_type == _BLOCK_EXTENDED_LINEAR_ADDR:
            if block_len != 2:
                raise ValueError('Extended address length not 2 bytes')
            extended_address = int.from_bytes(block_data, 'big')
        elif record_type == _BLOCK_PROGRAM_DATA:
            if not extended_address:
                if num_banks is not None:
                    raise ValueError('Unexpected extra program data block')
                if block_len != 64:
                    raise ValueError('Program data block not 64 bytes long')
                if address != next_block_num * 64:
                    raise ValueError('Unexpected block address')
                blocks.append(block_data)
                next_block_num += 1
            else:
                if num_banks is None:
                    num_banks, remainder = divmod(len(blocks), BLOCKS_PER_BANK)
                    if remainder:
                        raise ValueError('Program data has incomplete banks')
                if extended_address == _EXTENDED_ADDRESS_SECURITY:
                    if block_len != 64:
                        raise ValueError('Security data block not 64 bytes long')
                    remaining_security_blocks = num_banks - len(security)
                    if not remaining_security_blocks:
                        raise ValueError('Too many security data records')
                    security.append(block_data[:32])
                    if remaining_security_blocks > 1:
                        security.append(block_data[32:])
                elif extended_address == _EXTENDED_ADDRESS_CHECKSUM:
                    if len(security) != num_banks:
                        raise ValueError('Not enough security data records')
                    if block_len != 2:
                        raise ValueError('Checksum data block not 2 bytes long')
                    device_checksum = block_data

    if not device_checksum:
        raise ValueError('Missing checksum data')

    if int.from_bytes(device_checksum, 'big') != (sum(sum(b) % 65536 for b in blocks) % 65536):
        raise ValueError('Incorrect checksum')

    return blocks, security, device_checksum


def main():
    parser = argparse.ArgumentParser(
        description='Intel hex file converter for PSoC1',
        epilog='''If none of the optional output files are specified, they will all be generated with default file
        names: <hex-file-stem>_program.bin, <hex-file-stem>_security.bin and
        <hex-file-stem>_checksum.bin'''
    )
    parser.add_argument('hex_file', help='Input Intel hex file to convert')
    parser.add_argument('--program', '-p', help='Output flash program data file')
    parser.add_argument('--security', '-s', help='Output security data file')
    parser.add_argument('--checksum', '-c', help='Output checksum data file')

    args = parser.parse_args()

    hex_path = pathlib.Path(args.hex_file)
    program_path = args.program
    security_path = args.security
    checksum_path = args.checksum
    if program_path is None and security_path is None and checksum_path is None:
        program_path = hex_path.with_name(hex_path.stem + '_program.bin')
        security_path = hex_path.with_name(hex_path.stem + '_security.bin')
        checksum_path = hex_path.with_name(hex_path.stem + '_checksum.bin')

    with open(hex_path, 'rt') as hex_file:
        program, security, checksum = read_hex_file(hex_file)

    if program_path is not None:
        with open(program_path, 'wb') as program_file:
            program_file.writelines(program)

    if security_path is not None:
        with open(security_path, 'wb') as security_file:
            security_file.writelines(security)

    if checksum_path is not None:
        with open(checksum_path, 'wb') as checksum_file:
            checksum_file.write(checksum)


if __name__ == '__main__':
    main()