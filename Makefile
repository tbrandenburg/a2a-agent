SHELL := /bin/bash
.PHONY: test

test:
	@set -euo pipefail; \
	uv run python mcp_server.py & \
	MCP_PID=$$!; \
	sleep 5; \
	uv run python server_mcp.py & \
	SERVER_PID=$$!; \
	trap 'kill $$MCP_PID $$SERVER_PID' EXIT; \
	sleep 5; \
	uv run python fasta2a_client.py
