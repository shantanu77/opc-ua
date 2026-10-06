# OPC-UA simulator architecture

The simulator has two exclusive source modes: XML and manual. XML mode imports
only the selected NodeSet and reads its embedded SIMULATOR CONFIG. Manual mode
creates SimulatedDevice.Tag0000… using the manual form; no XML is imported.

The value producer updates nodes according to the effective source configuration.
The preview API describes initial values, ranges, units, patterns, parameters,
update interval and rule source. Live values are read directly from OPC-UA nodes.

The application provides one OPC-UA server for external clients. It does not
create internal load clients. Metrics count generated value updates and errors.

Uploads are validated before replacing the previous accepted file, automatically
select XML mode and refresh the preview. Source changes require a stopped run.
See readmev2.md for user instructions.
