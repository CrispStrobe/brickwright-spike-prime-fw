# TI BTS runtime boundary

The loader code in this directory is MIT-licensed. The repository carries no
TI service pack. Hardware builds fetch the exact, unmodified file from TI; it
remains governed solely by TI's licence and may be used only with TI devices.
The simulation profile does not use this loader.

`ti_bts_loader` consumes a caller-supplied BTSB image without changing its
bytes. It recognizes the public 32-byte container header and action record
boundaries, forwards complete H4 command actions through callbacks, and checks
the corresponding standard HCI Command Complete or Command Status event. It
does not interpret vendor opcodes or their parameters.

The importer fetches the allowlisted `.bts` file and TI's licence from TI's git
at the pinned commit (or takes a local copy named by
`BRICKWRIGHT_TI_SERVICE_PACK`), refuses any SHA-256 mismatch, and creates a
byte-for-byte C container below the ignored `.local/ti/` directory. It does not
decode or modify vendor commands.

The btsensor hardware adapter opens `/dev/ttyBT`, resets the controller, runs
the script before starting the Zephyr host, and closes the temporary loader
connection. Serial reconfiguration and delays are optional callbacks;
scripts that require an unavailable callback fail closed. Recursive script
actions and unknown actions are rejected.

Tests construct synthetic BTS records. They contain no TI firmware bytes.
