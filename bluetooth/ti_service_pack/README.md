# TI BTS runtime boundary

The loader code in this directory is MIT-licensed. The public source snapshot
also carries an exact, unmodified TI service pack under
`third_party/ti-cc2564c/`; that binary remains governed solely by its adjacent
TI licence and may be used only with TI devices.

`ti_bts_loader` consumes a caller-supplied BTSB image without changing its
bytes. It recognizes the public 32-byte container header and action record
boundaries, forwards complete H4 command actions through callbacks, and checks
the corresponding standard HCI Command Complete or Command Status event. It
does not interpret vendor opcodes or their parameters.

The importer verifies the allowlisted `.bts` file and creates a byte-for-byte C
container below the ignored `.local/ti/` directory. The build uses the vendored
official file by default. It does not decode or modify vendor commands.

The btsensor hardware adapter opens `/dev/ttyBT`, resets the controller, runs
the script before starting the Zephyr host, and closes the temporary loader
connection. Serial reconfiguration and delays are optional callbacks;
scripts that require an unavailable callback fail closed. Recursive script
actions and unknown actions are rejected.

Tests construct synthetic BTS records. They contain no TI firmware bytes.
