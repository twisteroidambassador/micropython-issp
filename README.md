# micropython-issp

Now you can program a Cypress PSoC1 device from a PyBoard!

## Overview

To program a PSoC1 device, in general follow these steps:

1. Prepare hardware. Refer to Cypress's [ISSP Programming Specification document](https://www.cypress.com/file/42201) for the required connections. At the very least, you need 2 GPIOs for SCLK and SDATA, and one additional GPIO either connected to XRES or controlling the target's power. Make sure to use 5V-tolerant GPIO pins if the target is powered by 5V.

2. Edit `issp.py` to match the hardware resources used.

3. On a computer, use `intelhex.py` to convert the .hex file produced by PSoC Designer into a binary file.

4. Copy `issp.py` and the binary program file to the PyBoard.

5. Connect the PyBoard to the target device and your computer. Open a REPL terminal to the PyBoard.

6. Put the target in programming mode using either `issp.reset()` or `issp.power_cycle_init`, and verify its silicon ID with `issp.read_id_word()`.

7. Read program data into memory, and program it into the target with `issp.program()` or `issp.patch()`.

8. Verify the result with `issp.verify()`.
