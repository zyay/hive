"""
AI Agent as P2P Peer — agents have their own identity and can participate
in P2P conversations. Supports both local (Ollama) and cloud (OpenAI, etc.) providers.
"""

import json
import time
import logging
from dataclasses import dataclass

from hive.core.identity import Identity, generate_identity
from hive.core.signal_protocol import SessionManager, SignalSession

logger = logging.getLogger(__name__)


@dataclass
class AgentPeer:
    """An AI agent that participates in P2P communication."""
    identity: Identity
    name: str
    system_prompt: str
    provider: str  # "ollama", "openai", "anthropic", etc.
    model: str
    use_local: bool = True  # True = Ollama, False = cloud API
    session_manager: SessionManager = None

    def __post_init__(self):
        if self.session_manager is None:
            self.session_manager = SessionManager()

    @property
    def did(self) -> str:
        return self.identity.did

    @property
    def peer_id(self) -> str:
        return self.identity.peer_id

    def to_dict(self) -> dict:
        return {
            "did": self.did,
            "peer_id": self.peer_id,
            "name": self.name,
            "provider": self.provider,
            "model": self.model,
            "use_local": self.use_local,
            "public_signing_key": self.identity.public_signing_key_hex,
            "public_encryption_key": self.identity.public_encryption_key_hex,
        }


def create_agent_peer(
    name: str,
    system_prompt: str,
    provider: str = "ollama",
    model: str = "",
    use_local: bool = True,
) -> AgentPeer:
    """Create a new AI agent with its own P2P identity."""
    identity = generate_identity(display_name=name)
    agent = AgentPeer(
        identity=identity,
        name=name,
        system_prompt=system_prompt,
        provider=provider,
        model=model,
        use_local=use_local,
    )
    logger.info(f"Created agent peer: {name} ({agent.did})")
    return agent


async def agent_respond(agent: AgentPeer, message: str, conversation_history: list[dict] = None) -> str:
    """
    Generate a response from the agent.
    Routes to local (Ollama) or cloud API based on agent config.
    """
    # Build messages for the LLM
    messages = [{"role": "system", "content": agent.system_prompt}]
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": message})

    if agent.use_local:
        return await _respond_local(agent, messages)
    else:
        return await _respond_cloud(agent, messages)


async def _respond_local(agent: AgentPeer, messages: list[dict]) -> str:
    """Generate response using local Ollama."""
    import httpx

    model = agent.model or "llama3.2"
    prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                "http://localhost:11434/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            return resp.json()["response"].strip()
    except Exception as e:
        logger.error(f"Local LLM error: {e}")
        return f"[Agent error: {e}]"


async def _respond_cloud(agent: AgentPeer, messages: list[dict]) -> str:
    """Generate response using cloud API (OpenAI-compatible)."""
    from hive.core.llm import chat

    try:
        resp = await chat(
            provider=agent.provider,
            model=agent.model,
            messages=messages,
        )
        return resp.content
    except Exception as e:
        logger.error(f"Cloud LLM error: {e}")
        return f"[Agent error: {e}]"


async def handle_agent_message(
    agent: AgentPeer,
    sender_did: str,
    encrypted_message: dict,
    session: SignalSession,
) -> dict:
    """
    Handle an incoming message for an agent peer.
    Decrypts, generates response, encrypts, and returns.
    """
    # Decrypt the message
    try:
        plaintext = session.decrypt(encrypted_message)
        data = json.loads(plaintext)
        content = data.get("content", "")
    except Exception as e:
        logger.error(f"Agent decrypt error: {e}")
        return {"error": str(e)}

    # Generate response
    response_text = await agent_respond(agent, content)

    # Encrypt the response
    response_data = json.dumps({
        "content": response_text,
        "sender": agent.did,
        "timestamp": time.time(),
        "type": "agent_response",
    })
    encrypted_response = session.encrypt(response_data)

    return {
        "encrypted": encrypted_response,
        "sender_did": agent.did,
        "timestamp": time.time(),
    }


class AgentRegistry:
    """Registry of all agent peers on this node."""

    def __init__(self):
        self._agents: dict[str, AgentPeer] = {}  # did -> AgentPeer

    def register(self, agent: AgentPeer):
        self._agents[agent.did] = agent
        logger.info(f"Registered agent: {agent.name} ({agent.did})")

    def get(self, did: str) -> AgentPeer | None:
        return self._agents.get(did)

    def get_by_name(self, name: str) -> AgentPeer | None:
        for agent in self._agents.values():
            if agent.name.lower() == name.lower():
                return agent
        return None

    def list_agents(self) -> list[dict]:
        return [a.to_dict() for a in self._agents.values()]

    def remove(self, did: str):
        self._agents.pop(did, None)

    def save(self, path: str = "agents.json"):
        """Save agent configs (not keys — those stay in keystore)."""
        data = {did: {
            "name": a.name,
            "system_prompt": a.system_prompt,
            "provider": a.provider,
            "model": a.model,
            "use_local": a.use_local,
        } for did, a in self._agents.items()}
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
