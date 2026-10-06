> Historical design notes. The current application serves OPC-UA only; see README.md and readmev2.md.

# Future PLC Protocol Implementation Notes

This document records the native PLC protocols to consider beyond the OPC-UA simulator. These are future items and are not implemented by the current application.

## Siemens

For direct PLC tag access, Siemens systems commonly use **S7 communication over ISO-on-TCP**. **PROFINET** is primarily the real-time field network between controllers, remote I/O, drives, and devices. Newer S7-1200 and S7-1500 CPUs can also expose OPC-UA.

The practical simulator target for a Brabo.io Siemens connector is an S7 endpoint rather than a complete PROFINET device.

Configuration will need:

- PLC family: S7-300/400 or S7-1200/1500
- Rack and slot
- Data block number
- Memory area: DB, input, output, marker, timer, or counter
- Byte and bit offset
- Siemens data type and byte order
- Absolute versus symbolic addressing
- Optimized versus non-optimized data blocks for newer PLCs
- Read/write permission
- Per-tag signal pattern, update rate, quality, and metadata

Implementation should begin only after recording the exact Brabo.io Siemens connector mode and supported PLC families.

## Allen-Bradley / Rockwell Automation

CompactLogix and ControlLogix use **EtherNet/IP with the Common Industrial Protocol (CIP)**. Brabo.io tag ingestion will normally use CIP explicit messaging to browse, read, and write named controller tags. Cyclic implicit I/O is a separate, more advanced scope.

Older SLC and MicroLogix controllers may use PCCC over EtherNet/IP or serial DF1 rather than the Logix symbolic-tag services.

Configuration will need:

- PLC family: CompactLogix, ControlLogix, MicroLogix, or SLC
- Controller/backplane path and slot
- Named tags for Logix controllers
- PCCC file addresses for SLC/MicroLogix
- Atomic type, arrays, and eventually structure definitions
- CIP class/instance/attribute mapping where applicable
- Read/write permission
- Per-tag signal pattern, update rate, quality, and metadata

Implementation should target CompactLogix/ControlLogix named tags first unless the Brabo.io connector requirement says otherwise.

## Recommended future adapters

1. `siemens_s7`: initially the smallest S7 profile used by Brabo.io.
2. `allen_bradley_logix`: initially EtherNet/IP/CIP explicit named-tag reads and writes.
3. Add PCCC, PROFINET, or cyclic CIP I/O only from demonstrated ingestion requirements.

Useful references:

- [Siemens OPC-UA and PROFINET positioning](https://www.siemens.com/en-us/products/opc-ua/)
- [Rockwell CompactLogix EtherNet/IP communication](https://literature.rockwellautomation.com/idc/groups/literature/documents/um/1769-um011_-en-p.pdf)
- [ODVA EtherNet/IP overview](https://www.odva.org/technology-standards/key-technologies/ethernet-ip/)
