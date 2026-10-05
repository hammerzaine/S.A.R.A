#!/usr/bin/env python3
"""
Tool-Calling Agent Wrapper

A lightweight wrapper around the agent bridge that adds tool-calling capability
for the web UI. Uses the providers' native chat_with_messages() method to send
tool definitions to the LLM and receive structured tool call responses.
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from tools.registry import registry, discover_builtin_tools

logger = logging.getLogger(__name__)

# Discover tools on module import
discover_builtin_tools()


def _sanitize_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Remove fields that Gemini doesn't support in function declarations."""
    if not isinstance(schema, dict):
        return schema
    sanitized = {}
    for key, value in schema.items():
        if key == "additionalProperties":
            continue
        if key == "default":
            continue
        if key == "enum" and isinstance(value, list):
            # Gemini requires enum values to be strings
            sanitized[key] = [str(v) for v in value]
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_schema(value)
        elif isinstance(value, list):
            sanitized[key] = [_sanitize_schema(item) if isinstance(item, dict) else item for item in value]
        else:
            sanitized[key] = value
    return sanitized


def _get_tool_definitions() -> List[Dict[str, Any]]:
    """Get OpenAI-format tool definitions for all registered tools."""
    tools = []
    for name in registry.get_all_tool_names():
        entry = registry.get_entry(name)
        if entry and entry.schema:
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": entry.schema.get("description", ""),
                    "parameters": _sanitize_schema(entry.schema.get("parameters", {"type": "object", "properties": {}}))
                }
            })
    return tools


def _execute_tool(name: str, arguments: Dict[str, Any]) -> str:
    """Execute a tool by name with given arguments."""
    try:
        entry = registry.get_entry(name)
        if not entry or not entry.handler:
            return f"Error: Tool '{name}' not found"

        result = entry.handler(arguments)
        if isinstance(result, dict):
            return json.dumps(result, indent=2)
        return str(result)
    except Exception as e:
        logger.error(f"Tool execution failed: {name} - {e}")
        return f"Error executing {name}: {str(e)}"


def chat_with_tools(
    agent,
    message: str,
    stream_callback: Optional[Callable[[str], None]] = None,
    max_iterations: int = 10,
    history: Optional[List[Dict[str, str]]] = None
) -> str:
    """Process a message with tool-calling support.

    Uses the provider's native chat_with_messages() for structured tool calls.
    Falls back to text-only if the provider doesn't support it.

    Args:
        agent: The agent bridge instance
        message: User message
        stream_callback: Optional streaming callback
        max_iterations: Maximum tool-calling iterations
        history: Previous conversation history (list of {role, content} dicts)

    Returns:
        Final text response from the agent
    """
    tool_definitions = _get_tool_definitions()

    system_prompt = (
        "You are S.A.R.A, a helpful AI assistant. "
        "You have access to tools that can help you answer questions. "
        "Use tools when necessary to answer the user's question."
    )

    # Build conversation messages with history
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
    ]

    # Add previous conversation history (limit to last 20 messages to avoid token limits)
    if history:
        messages.extend(history[-20:])

    # Add current user message
    messages.append({"role": "user", "content": message})
    for iteration in range(max_iterations):
        # Use the provider's native tool-calling method
        result = agent.chat_with_messages(
            messages,
            tools=tool_definitions,
            stream_callback=stream_callback
        )

        content = result.get("content", "")
        tool_calls = result.get("tool_calls", [])

        if not tool_calls:
            # No tool calls, return the text response
            return content

        # Execute tool calls and build follow-up messages
        messages.append({"role": "assistant", "content": content})

        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("arguments", {})
            logger.info(f"Executing tool: {name} with args: {args}")
            tool_result = _execute_tool(name, args)
            # Gemini doesn't support role="tool", so format as user message
            messages.append({
                "role": "user",
                "content": f"Tool result from {name}: {tool_result}"
            })

    return "Error: Maximum tool-calling iterations reached"
