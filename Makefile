SHELL := /bin/bash
.PHONY: test

test:
	@set -euo pipefail; \
	uv run python mcp_server.py & \
	MCP_PID=$$!; \
	uv run python server_mcp.py & \
	SERVER_PID=$$!; \
	trap 'kill $$MCP_PID $$SERVER_PID' EXIT; \
	sleep 1; \
	uv run python fasta2a_client.py
