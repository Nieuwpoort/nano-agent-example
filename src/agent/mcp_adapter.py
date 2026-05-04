import json
import logging
import re
from os import getenv
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
import requests


MCP_TOOLSET_BASE_URL = getenv("MCP_TOOLSET_BASE_URL", "http://127.0.0.1:3123").rstrip("/")


TOOLS: list[dict[str, Any]] = [
    {
        "name": "wallet.balance",
        "description": "Get wallet balance and pending amount.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "wallet.send",
        "description": "Send Nano to a recipient address.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "recipient_address": {"type": "string"},
                "amount": {"type": "string"},
            },
            "required": ["recipient_address", "amount"],
        },
    },
    {
        "name": "payment.request",
        "description": "Create a payment request.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "receive_address": {"type": "string"},
                "amount": {"type": "string"},
                "redirect_url": {"type": ["string", "null"]},
            },
            "required": ["receive_address", "amount"],
        },
    },
    {
        "name": "payment.status",
        "description": "Get payment status by transaction id.",
        "inputSchema": {
            "type": "object",
            "properties": {"transaction_id": {"type": "string"}},
            "required": ["transaction_id"],
        },
    },
    {
        "name": "credits.get",
        "description": "Get available credits and price tiers.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "credits.topup",
        "description": "Top up credits by predefined tier.",
        "inputSchema": {
            "type": "object",
            "properties": {"credits_amount": {"type": "integer"}},
            "required": ["credits_amount"],
        },
    },
    {
        "name": "donate.send",
        "description": "Send a Nano donation.",
        "inputSchema": {
            "type": "object",
            "properties": {"amount": {"type": "string"}},
            "required": ["amount"],
        },
    },
]


class MCPAdapter:
    def __init__(self):
        self.base_url = MCP_TOOLSET_BASE_URL
        self._validate_connection()

    def _validate_connection(self) -> None:
        try:
            response = requests.get(self.base_url, timeout=2)
            logging.info(f"✅ MCP toolset reachable at startup (probe status: {response.status_code})")
        except Exception as error:
            logging.info(f"MCP toolset not reachable at startup, will retry on requests: {error}")

    def process(
        self,
        message: str,
        invoke_llm: Callable[[list[Any]], str],
        system_prompt: str,
    ) -> str:
        try:
            direct_tool = self._select_direct_tool(message)
            if direct_tool is not None:
                tool_name, arguments = direct_tool
                arguments = self._prepare_tool_arguments(tool_name, arguments)
                tool_result = self._call_tool(tool_name, arguments)
                deterministic_error = self._deterministic_tool_error(tool_result)
                if deterministic_error:
                    return deterministic_error
                deterministic_success = self._deterministic_tool_success(tool_name, tool_result, message, arguments)
                if deterministic_success:
                    return deterministic_success
                return "MCP tool call completed successfully."

            tools = self._list_tools()
            if not tools:
                return invoke_llm([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=message),
                ])

            decision_prompt = self._build_tool_decision_prompt(tools)
            decision_raw = invoke_llm([
                SystemMessage(content=system_prompt),
                SystemMessage(content=decision_prompt),
                HumanMessage(content=message),
            ])

            decision = self._extract_json_object(decision_raw)
            if not isinstance(decision, dict):
                return invoke_llm([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=message),
                ])

            if not decision.get("use_tool"):
                answer = decision.get("answer")
                if isinstance(answer, str) and answer.strip():
                    return answer.strip()
                return invoke_llm([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=message),
                ])

            tool_name = str(decision.get("tool", "")).strip()
            arguments = decision.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}
            arguments = self._prepare_tool_arguments(tool_name, arguments)

            available_tool_names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
            if tool_name not in available_tool_names:
                return "Requested MCP tool is not available."

            tool_result = self._call_tool(tool_name, arguments)
            deterministic_error = self._deterministic_tool_error(tool_result)
            if deterministic_error:
                return deterministic_error
            deterministic_success = self._deterministic_tool_success(tool_name, tool_result, message, arguments)
            if deterministic_success:
                return deterministic_success
            return "MCP tool call completed successfully."

        except Exception as error:
            logging.warning(f"MCP flow failed; falling back to plain LLM: {error}")
            return invoke_llm([
                SystemMessage(content=system_prompt),
                HumanMessage(content=message),
            ])

    def _select_direct_tool(self, message: str) -> tuple[str, dict[str, Any]] | None:
        normalized = message.lower()
        balance_markers = ["balance", "saldo", "wallet balance", "check balance"]
        if any(marker in normalized for marker in balance_markers):
            return ("wallet.balance", {})

        payment_status_args = self._extract_payment_status_arguments(message)
        if payment_status_args is not None:
            return ("payment.status", payment_status_args)

        send_args = self._extract_send_arguments(message)
        if send_args is not None:
            return ("wallet.send", send_args)

        payment_request_args = self._extract_payment_request_arguments(message)
        if payment_request_args is not None:
            return ("payment.request", payment_request_args)

        return None

    def _synthesize_tool_result(
        self,
        message: str,
        tool_name: str,
        arguments: dict[str, Any],
        tool_result: dict[str, Any],
        invoke_llm: Callable[[list[Any]], str],
        system_prompt: str,
    ) -> str:
        synthesis_prompt = (
            "You executed an MCP tool. Generate the final user-facing answer in plain language. "
            "If the tool failed, explain the error clearly and suggest the next action."
        )

        return invoke_llm([
            SystemMessage(content=system_prompt),
            SystemMessage(content=synthesis_prompt),
            HumanMessage(content=f"User request: {message}"),
            AIMessage(content=f"Tool used: {tool_name} with args {json.dumps(arguments, ensure_ascii=False)}"),
            AIMessage(content=f"Tool result: {json.dumps(tool_result, ensure_ascii=False)}"),
        ])

    def _deterministic_tool_error(self, tool_result: dict[str, Any]) -> str | None:
        if not isinstance(tool_result, dict):
            return None

        success = tool_result.get("success")
        if success is True:
            return None

        error = tool_result.get("error")
        status = tool_result.get("status")
        if not isinstance(error, dict):
            return None

        code = str(error.get("error", "TOOL_ERROR"))
        message = str(error.get("message", "Unknown tool error"))

        if status == 503 and code == "MCP_UNREACHABLE":
            return "MCP toolset is not reachable from the agent. Ensure the plugin API is running and reachable at MCP_TOOLSET_BASE_URL."

        if status == 502 and code == "PARSE_ERROR":
            return (
                "MCP toolset reached upstream, but upstream returned an unexpected response format (502 PARSE_ERROR). "
                "Check plugin upstream configuration (for example IFENPAY_API_URL) and verify the upstream payment/status endpoint returns valid JSON."
            )

        if status == 502:
            return f"MCP toolset is reachable, but its upstream service failed (502 {code}): {message}"

        return f"MCP tool call failed ({code}): {message}"

    def _deterministic_tool_success(
        self,
        tool_name: str,
        tool_result: dict[str, Any],
        message: str,
        arguments: dict[str, Any],
    ) -> str | None:
        if not isinstance(tool_result, dict) or tool_result.get("success") is not True:
            return None

        data = tool_result.get("data")

        if tool_name == "wallet.balance":
            if isinstance(data, dict):
                account = data.get("account")
                balance = data.get("balance")
                pending = data.get("pending")
                if account is not None and balance is not None and pending is not None:
                    return f"Wallet balance for {account}: {balance} NANO (pending: {pending} NANO)."
                if balance is not None and pending is not None:
                    return f"Wallet balance: {balance} NANO (pending: {pending} NANO)."
            return "Wallet balance retrieved successfully."

        if tool_name == "wallet.send":
            if isinstance(data, dict):
                amount = data.get("amount")
                recipient = data.get("recipient")
                if amount is not None and recipient is not None:
                    return f"Transfer submitted successfully: {amount} NANO sent to {recipient}."
            return "Transfer submitted successfully."

        if tool_name == "payment.request":
            if isinstance(data, dict):
                receive_address = data.get("receive_address") or arguments.get("receive_address")
                amount = data.get("amount")
                transaction_id = data.get("transaction_id")
                if amount is not None and transaction_id is not None and receive_address:
                    return (
                        f"Payment request created: {amount} NANO to {receive_address}. "
                        f"Transaction ID: {transaction_id}."
                    )
                if amount is not None and transaction_id is not None:
                    return (
                        f"Payment request created: {amount} NANO. "
                        f"Transaction ID: {transaction_id}. Destination address was not returned by the tool."
                    )
            return "Payment request created successfully."

        if tool_name == "payment.status":
            if isinstance(data, dict):
                transaction_id = data.get("transaction_id")
                is_paid = data.get("is_paid")
                status_text = "paid" if is_paid is True else "not paid"
                if transaction_id is not None:
                    return f"Payment status for {transaction_id}: {status_text}."
                return f"Payment status: {status_text}."
            return "Payment status retrieved successfully."

        if tool_name != "credits.get":
            if tool_name == "credits.topup":
                if isinstance(data, dict):
                    topped_up = data.get("topped_up_credits")
                    new_balance = data.get("new_credits_balance")
                    if topped_up is not None and new_balance is not None:
                        return f"Credits topped up: +{topped_up}. New credits balance: {new_balance}."
                return "Credits topped up successfully."

            if tool_name == "donate.send":
                if isinstance(data, dict):
                    amount = data.get("amount")
                    donate_success = data.get("success")
                    if amount is not None:
                        if donate_success is True:
                            return f"Donation sent successfully: {amount} NANO."
                        return f"Donation request processed for {amount} NANO."
                return "Donation request processed successfully."

            return f"MCP tool '{tool_name}' completed successfully."

        if not isinstance(data, dict):
            return None

        requested_amount = self._extract_requested_credits_amount(message)
        if requested_amount is not None:
            key = f"current_credits_price_{requested_amount}"
            if key in data:
                return f"The current price of {requested_amount} credits is {data[key]} NANO."

        price_items: list[tuple[int, Any]] = []
        for key, value in data.items():
            match = re.fullmatch(r"current_credits_price_(\d+)", str(key))
            if not match:
                continue
            price_items.append((int(match.group(1)), value))

        if not price_items:
            return None

        price_items.sort(key=lambda item: item[0])
        lines = [f"{amount} credits: {value} NANO" for amount, value in price_items]
        return "Current credit prices (NANO):\n" + "\n".join(lines)

    def _extract_requested_credits_amount(self, message: str) -> int | None:
        match = re.search(r"(\d+)\s*credits?", message.lower())
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _extract_send_arguments(self, message: str) -> dict[str, str] | None:
        normalized = message.lower()
        if "send" not in normalized:
            return None

        address_match = re.search(r"\b(?:nano|xrb)_[13][13456789abcdefghijkmnopqrstuwxyz]{59}\b", message)
        amount_match = re.search(r"(\d+(?:\.\d+)?)\s*nano\b", normalized)

        if not address_match or not amount_match:
            return None

        return {
            "recipient_address": address_match.group(0),
            "amount": amount_match.group(1),
        }

    def _extract_payment_status_arguments(self, message: str) -> dict[str, str] | None:
        normalized = message.lower()
        status_markers = ["payment status", "status payment", "get payment status", "check payment status"]
        if not any(marker in normalized for marker in status_markers):
            return None

        transaction_id = self._extract_transaction_id(message)
        if not transaction_id:
            return None

        return {"transaction_id": transaction_id}

    def _extract_payment_request_arguments(self, message: str) -> dict[str, str] | None:
        normalized = message.lower()
        request_markers = ["payment request", "create payment request", "request payment", "betaalverzoek"]
        if not any(marker in normalized for marker in request_markers):
            return None

        amount_match = re.search(r"(\d+(?:\.\d+)?)\s*nano\b", normalized)
        if not amount_match:
            return None

        receive_address = self._extract_nano_address(message)
        if not receive_address:
            balance_result = self._call_tool("wallet.balance", {})
            balance_data = balance_result.get("data") if isinstance(balance_result, dict) else None
            if isinstance(balance_data, dict):
                account = balance_data.get("account")
                if isinstance(account, str) and account.strip():
                    receive_address = account.strip()

        if not receive_address:
            return None

        return {
            "receive_address": receive_address,
            "amount": amount_match.group(1),
        }

    def _extract_nano_address(self, text: str) -> str | None:
        address_match = re.search(r"\b(?:nano|xrb)_[13][13456789abcdefghijkmnopqrstuwxyz]{59}\b", text)
        if not address_match:
            return None
        return address_match.group(0)

    def _prepare_tool_arguments(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "payment.status":
            prepared_status = dict(arguments)
            transaction_id = prepared_status.get("transaction_id")
            extracted = self._extract_transaction_id(str(transaction_id) if transaction_id is not None else "")
            if extracted:
                prepared_status["transaction_id"] = extracted
            return prepared_status

        if tool_name != "payment.request":
            return arguments

        prepared = dict(arguments)
        receive_address = prepared.get("receive_address")

        if self._is_placeholder_address(receive_address):
            resolved = self._resolve_wallet_receive_address()
            if resolved:
                prepared["receive_address"] = resolved

        return prepared

    def _is_placeholder_address(self, value: Any) -> bool:
        if value is None:
            return True
        if not isinstance(value, str):
            return True

        candidate = value.strip()
        if not candidate:
            return True
        if candidate.startswith("<") and candidate.endswith(">"):
            return True
        if "receiving_address" in candidate.lower():
            return True
        if self._extract_nano_address(candidate) is None:
            return True
        return False

    def _resolve_wallet_receive_address(self) -> str | None:
        balance_result = self._call_tool("wallet.balance", {})
        if not isinstance(balance_result, dict) or balance_result.get("success") is not True:
            return None

        data = balance_result.get("data")
        if not isinstance(data, dict):
            return None

        account = data.get("account")
        if not isinstance(account, str) or not account.strip():
            return None

        return account.strip()

    def _extract_transaction_id(self, text: str) -> str | None:
        match = re.search(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", text)
        if not match:
            return None
        return match.group(0)

    def _list_tools(self) -> list[dict[str, Any]]:
        return TOOLS

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "wallet.balance":
            return self._http("GET", "/wallet/balance")
        if name == "wallet.send":
            return self._http("POST", "/wallet/send", json_body=arguments)
        if name == "payment.request":
            return self._http("POST", "/payment/request", json_body=arguments)
        if name == "payment.status":
            transaction_id = str(arguments.get("transaction_id", "")).strip()
            if not transaction_id:
                raise RuntimeError("payment.status requires transaction_id")
            return self._http("GET", f"/payment/status/{transaction_id}")
        if name == "credits.get":
            return self._http("GET", "/credits")
        if name == "credits.topup":
            credits_amount = arguments.get("credits_amount")
            if credits_amount is None:
                raise RuntimeError("credits.topup requires credits_amount")
            return self._http("POST", f"/credits/topup/{credits_amount}")
        if name == "donate.send":
            amount = str(arguments.get("amount", "")).strip()
            if not amount:
                raise RuntimeError("donate.send requires amount")
            return self._http("POST", f"/donate/{amount}")

        raise RuntimeError(f"Unknown tool: {name}")

    def _http(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = requests.request(
                method=method,
                url=f"{self.base_url}{path}",
                json=json_body,
                timeout=30,
            )
        except requests.RequestException as error:
            return {
                "success": False,
                "status": 503,
                "error": {
                    "error": "MCP_UNREACHABLE",
                    "message": str(error),
                },
            }

        try:
            payload = response.json()
        except Exception:
            payload = {"success": False, "data": None, "error": {"error": "INVALID_JSON", "message": response.text}}

        if isinstance(payload, dict) and "status" not in payload:
            payload["status"] = response.status_code

        return payload if isinstance(payload, dict) else {"result": payload, "status": response.status_code}

    def _build_tool_decision_prompt(self, tools: list[dict[str, Any]]) -> str:
        catalog = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            catalog.append(
                {
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema", {"type": "object", "properties": {}}),
                }
            )

        return (
            "You are deciding whether to call an MCP tool. "
            "Return ONLY valid JSON with one of these shapes:\n"
            "1) {\"use_tool\": false, \"answer\": \"...\"}\n"
            "2) {\"use_tool\": true, \"tool\": \"tool.name\", \"arguments\": {...}}\n"
            "Do not wrap in markdown.\n"
            f"Available tools: {json.dumps(catalog, ensure_ascii=False)}"
        )

    def _extract_json_object(self, text: str) -> dict[str, Any] | None:
        if not text:
            return None

        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        try:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
