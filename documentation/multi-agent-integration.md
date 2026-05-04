# Multi-Agent Integration (Minimal Pattern)

This pattern is framework-agnostic and can be reused in LangChain, OpenAI SDK agents, custom Python, Node.js, or Rust agents.

## Core rule

Treat the toolset as an external dependency and call it through one configured base URL.

## Minimal implementation checklist

1. Read base URL from env (for example `MCP_TOOLSET_BASE_URL`).
2. Validate user intent and required arguments.
3. Call the matching tool endpoint.
4. Branch on `success`.
5. Use `error.error` as machine key and `error.message` as human text.
6. Return deterministic outputs for side-effect actions (for example transfers).

## HTTP endpoints used by this example

- `GET /wallet/balance`
- `POST /wallet/send`
- `POST /payment/request`
- `GET /payment/status/{transaction_id}`
- `GET /credits`
- `POST /credits/topup/{credits_amount}`
- `POST /donate/{amount}`

## MCP-native clients

If your framework supports MCP directly:

- Call `initialize`
- Call `tools/list`
- Call `tools/call`

The behavioral contract remains the same.

## Recommended behavior for autonomous agents

- Prefer deterministic formatting for action results.
- Do not hide failed tool calls behind generic LLM text.
- Log `error.error` for observability and retries.
- Keep side effects explicit and auditable.

## Canonical references

Use the `ifenpay-nano-toolset` repository as source of truth for:

- OpenAPI schema
- MCP method/tool contract
- Error enum catalog
