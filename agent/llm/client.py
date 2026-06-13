"""LLM client for the coding agent using Google Gemini or OpenAI-compatible local models.

Supports:
- Google Gemini via google-genai SDK
- Local models (Ollama, vLLM) via OpenAI SDK
"""
import os
import json
from typing import List, Dict, Any, Optional

from google import genai
from google.genai import types


class GeminiClient:
    """Client for interacting with Google Gemini API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.0-flash",
        temperature: float = 0.2,
        max_tokens: int = 4000,
        **kwargs,  # Accept and ignore extra kwargs like base_url
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "No API key provided. Set GEMINI_API_KEY environment variable "
                "or pass api_key to the constructor."
            )

        self.client = genai.Client(api_key=self.api_key)
        self.model_name = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
    ) -> Dict[str, Any]:
        try:
            system_instruction, contents = self._convert_messages(messages)
            gemini_tools = self._convert_tools(tools) if tools else None

            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=gemini_tools,
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )

            if getattr(response, "prompt_feedback", None):
                block_reason = getattr(response.prompt_feedback, "block_reason", None)
                if block_reason:
                    return {
                        "content": f"Response blocked by safety filters. Reason: {block_reason}",
                        "tool_calls": [],
                        "finish_reason": "safety",
                    }

            return self._parse_response(response)

        except Exception as e:
            return {
                "content": "",
                "error": f"Gemini API error: {str(e)}",
                "finish_reason": "error",
            }

    def simple_chat(self, system_prompt: str, user_message: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        response = self.chat(messages)
        return response.get("content", "")

    def _convert_messages(self, messages):
        system_instruction = None
        contents = []
        tc_id_to_name: Dict[str, str] = {}

        for msg in messages:
            role = msg.get("role")
            if role == "system":
                system_instruction = msg["content"]
            elif role == "user":
                contents.append(
                    types.Content(role="user", parts=[types.Part.from_text(text=msg["content"])])
                )
            elif role == "assistant":
                if msg.get("tool_calls"):
                    parts = []
                    for tc in msg["tool_calls"]:
                        fn = tc.get("function", tc)
                        name = fn.get("name", "")
                        args_raw = fn.get("arguments", "{}")
                        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                        tc_id_to_name[tc.get("id", "")] = name
                        parts.append(types.Part.from_function_call(name=name, args=args))
                    contents.append(types.Content(role="model", parts=parts))
                else:
                    content = msg.get("content", "")
                    if content:
                        contents.append(
                            types.Content(role="model", parts=[types.Part.from_text(text=content)])
                        )
            elif role == "tool":
                tc_id = msg.get("tool_call_id", "")
                fn_name = tc_id_to_name.get(tc_id, "unknown")
                result_str = msg["content"]
                try:
                    result_dict = json.loads(result_str)
                    if not isinstance(result_dict, dict):
                        result_dict = {"result": result_dict}
                except:
                    result_dict = {"result": result_str}
                contents.append(
                    types.Content(
                        parts=[types.Part.from_function_response(name=fn_name, response=result_dict)]
                    )
                )

        return system_instruction, contents

    def _convert_tools(self, openai_tools):
        declarations = []
        for tool in openai_tools:
            fn = tool.get("function", {})
            params = self._clean_schema(fn.get("parameters", {}))
            decl = {"name": fn.get("name", ""), "description": fn.get("description", "")}
            if params:
                decl["parameters"] = params
            declarations.append(decl)
        return [{"function_declarations": declarations}]

    def _clean_schema(self, schema):
        if not isinstance(schema, dict):
            return schema
        cleaned = {}
        supported = {"type", "description", "properties", "required", "items", "enum"}
        for key, value in schema.items():
            if key not in supported:
                continue
            if key == "properties":
                cleaned[key] = {k: self._clean_schema(v) for k, v in value.items()}
            elif key == "items":
                cleaned[key] = self._clean_schema(value)
            else:
                cleaned[key] = value
        return cleaned

    def _parse_response(self, response):
        result: Dict[str, Any] = {"content": "", "tool_calls": [], "finish_reason": "stop"}
        if not response.candidates:
            return result
        candidate = response.candidates[0]
        if candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if getattr(part, "function_call", None):
                    fc = part.function_call
                    args = dict(fc.args) if fc.args else {}
                    result["tool_calls"].append({
                        "id": f"call_{fc.name}_{len(result['tool_calls'])}",
                        "name": fc.name,
                        "arguments": json.dumps(args),
                    })
                    result["finish_reason"] = "tool_calls"
                elif getattr(part, "text", None):
                    result["content"] += part.text

        usage_meta = getattr(response, "usage_metadata", None)
        if usage_meta:
            result["usage"] = {
                "prompt_tokens": getattr(usage_meta, "prompt_token_count", 0),
                "completion_tokens": getattr(usage_meta, "candidates_token_count", 0),
                "total_tokens": getattr(usage_meta, "total_token_count", 0),
            }
        return result


class OpenAIClient:
    """Client for OpenAI-compatible local endpoints like Ollama or vLLM."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "qwen2.5-coder:7b",
        base_url: str = "http://localhost:11434/v1",
        temperature: float = 0.2,
        max_tokens: int = 4000,
        **kwargs,
    ):
        try:
            import openai
        except ImportError:
            raise ImportError(
                "The 'openai' package is required for local models. "
                "Install it with: pip install openai"
            )

        # Use provided key or fall back to environment variable
        if api_key is None:
            api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "No OpenAI API key provided. Set OPENAI_API_KEY environment variable or pass api_key to the constructor."
            )

        self.client = openai.OpenAI(base_url=base_url, api_key=api_key)
        self.model_name = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
    ) -> Dict[str, Any]:
        try:
            kwargs = {
                "model": self.model_name,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice

            response = self.client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            result = {
                "content": choice.message.content or "",
                "tool_calls": [],
                "finish_reason": choice.finish_reason
            }

            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    result["tool_calls"].append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    })

            if response.usage:
                result["usage"] = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            return result
        except Exception as e:
            return {"content": "", "error": f"Local API error: {str(e)}", "finish_reason": "error"}

    def simple_chat(self, system_prompt: str, user_message: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        response = self.chat(messages)
        return response.get("content", "")


def LLMClient(provider: str = "gemini", **kwargs):
    """Factory to get the correct LLM client.
    
    If base_url is provided, it automatically switches to the OpenAI local client.
    """
    if provider == "openai" or kwargs.get("base_url"):
        return OpenAIClient(**kwargs)
    return GeminiClient(**kwargs)
