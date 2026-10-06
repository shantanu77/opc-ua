# OPC-UA configuration workflow

The application serves OPC-UA only. Its default source is `config_data.xml`.
Tag data, engineering metadata and the embedded simulator JSON are loaded without
requiring separate API configuration. See [readmev2.md](readmev2.md) for the rules,
loaded/live tag table, Docker instructions and API.

Configure & Run shows the loaded XML tags before starting. Live Data shows values
read directly from the running OPC-UA server. Save Draft never opens a listener;
Start starts the OPC-UA server and value producer, and optionally internal load
clients. Stop closes all run tasks and the OPC-UA listener.
