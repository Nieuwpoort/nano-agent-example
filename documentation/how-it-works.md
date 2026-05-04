# How This Example Works

## High-level architecture

1. The example agent runs in Docker (`ifenpay-agent-example-private`).
2. The Nano toolset runs separately on the host (`ifenpay-nano-toolset`).
3. The agent connects to the toolset over HTTP via `MCP_TOOLSET_BASE_URL`.
4. User prompts are mapped to tool calls (balance, send, payment, etc.).
5. Tool responses are returned in a deterministic envelope (`success`, `data`, `error`).

## Runtime flow

- Start `ifenpay-nano-toolset` first.
- Start this example with `docker compose up --build`.
- The agent calls `http://host.docker.internal:3123` from inside the container.

## Why this is simple

- No plugin lifecycle management inside the agent
- One base URL for all tool operations
- Same response shape for all calls
- Framework-specific code stays thin; tool logic remains in the toolset

## Responsibility split

- Toolset repo: contracts, business logic, errors, wallet/payment internals
- Example repo: how to wire an agent runtime to the toolset
