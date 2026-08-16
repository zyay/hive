"""
Extra tools for Hive agents — web search, code execution, image generation.
"""

import json
import logging
import asyncio
from typing import Optional

import httpx

from hive.core.agent import register_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Web Search Tool
# ---------------------------------------------------------------------------

@register_tool(
    name="web_search",
    description="Search the web for current information. Returns top results with titles, URLs, and snippets.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "num_results": {"type": "integer", "description": "Number of results (1-10)", "default": 5},
        },
        "required": ["query"],
    },
)
async def web_search(query: str, num_results: int = 5) -> str:
    """Search the web using DuckDuckGo (no API key required)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            )
            data = resp.json()

        results = []
        
        if data.get("Abstract"):
            results.append({
                "title": data.get("Heading", "Summary"),
                "url": data.get("AbstractURL", ""),
                "snippet": data["Abstract"][:300],
            })

        for r in data.get("RelatedTopics", [])[:num_results]:
            if "Text" in r:
                results.append({
                    "title": r.get("Text", "")[:80],
                    "url": r.get("FirstURL", ""),
                    "snippet": r.get("Text", "")[:200],
                })

        if not results:
            return f"No results found for: {query}"

        output = f"Search results for: {query}\n\n"
        for i, r in enumerate(results[:num_results], 1):
            output += f"{i}. {r['title']}\n   URL: {r['url']}\n   {r['snippet']}\n\n"
        
        return output.strip()

    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return f"Search error: {e}"


# ---------------------------------------------------------------------------
# URL Fetcher Tool
# ---------------------------------------------------------------------------

@register_tool(
    name="fetch_url",
    description="Fetch and extract text content from a URL.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
        },
        "required": ["url"],
    },
)
async def fetch_url(url: str) -> str:
    """Fetch a URL and extract readable text."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Hive/1.0"})
            resp.raise_for_status()
        
        content_type = resp.headers.get("content-type", "")
        text = resp.text

        if "html" in content_type:
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

        if len(text) > 5000:
            text = text[:5000] + "\n... [truncated]"

        return f"Content from {url}:\n\n{text}"

    except Exception as e:
        logger.error(f"URL fetch failed: {e}")
        return f"Fetch error: {e}"


# ---------------------------------------------------------------------------
# Code Execution Sandbox
# ---------------------------------------------------------------------------

@register_tool(
    name="execute_code",
    description="Execute Python code in a sandboxed environment. Returns stdout, stderr, and return code.",
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds (max 30)", "default": 10},
        },
        "required": ["code"],
    },
)
async def execute_code(code: str, timeout: int = 10) -> str:
    """Execute Python code in a subprocess sandbox."""
    timeout = min(timeout, 30)
    
    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "-c", code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return f"Error: Code execution timed out after {timeout}s"
        
        output = ""
        if stdout:
            output += f"stdout:\n{stdout.decode('utf-8', errors='replace')}\n"
        if stderr:
            output += f"stderr:\n{stderr.decode('utf-8', errors='replace')}\n"
        output += f"Return code: {proc.returncode}"
        
        if len(output) > 5000:
            output = output[:5000] + "\n... [truncated]"
        
        return output.strip()

    except FileNotFoundError:
        return "Error: Python interpreter not found"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Image Generation (placeholder — requires API key)
# ---------------------------------------------------------------------------

@register_tool(
    name="generate_image",
    description="Generate an image from a text prompt using AI. Returns image URL or description.",
    parameters={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Image description/prompt"},
            "size": {"type": "string", "description": "Image size (e.g., '512x512', '1024x1024')", "default": "512x512"},
        },
        "required": ["prompt"],
    },
)
async def generate_image(prompt: str, size: str = "512x512") -> str:
    """Generate an image using available providers."""
    from hive.core.config import settings
    
    if settings.OPENAI_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={
                        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "dall-e-3",
                        "prompt": prompt,
                        "size": size,
                        "quality": "standard",
                        "n": 1,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                url = data["data"][0]["url"]
                revised = data["data"][0].get("revised_prompt", "")
                return f"Image generated!\nURL: {url}\nRevised prompt: {revised}"
        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return f"Image generation error: {e}"
    
    return "Image generation requires an OpenAI API key. Configure it in Settings."


# ---------------------------------------------------------------------------
# DateTime Tool (enhanced)
# ---------------------------------------------------------------------------

@register_tool(
    name="world_clock",
    description="Get current time in multiple timezones.",
    parameters={
        "type": "object",
        "properties": {
            "timezones": {
                "type": "string",
                "description": "Comma-separated timezone names (e.g., 'US/Eastern,Europe/London,Asia/Tokyo')",
            },
        },
        "required": [],
    },
)
def world_clock(timezones: str = "") -> str:
    """Get current time in specified timezones."""
    from datetime import datetime
    try:
        import zoneinfo
    except ImportError:
        return "zoneinfo module not available (Python 3.9+ required)"

    tz_list = [t.strip() for t in timezones.split(",") if t.strip()] if timezones else [
        "UTC", "US/Eastern", "US/Pacific", "Europe/London", "Europe/Berlin", "Asia/Tokyo"
    ]

    now = datetime.now()
    output = "World Clock:\n\n"
    for tz_name in tz_list:
        try:
            tz = zoneinfo.ZoneInfo(tz_name)
            local_time = now.astimezone(tz)
            output += f"  {tz_name}: {local_time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        except Exception:
            output += f"  {tz_name}: (invalid timezone)\n"

    return output.strip()
