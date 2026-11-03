"""Backend-agnostic LLM wrapper (Phase 4).

One interface, two interchangeable backends selected by the LLM_BACKEND env var:
  subscription -> Claude Agent SDK, the developer plan, local development only
  api          -> anthropic SDK with ANTHROPIC_API_KEY, for the deployed demo

MODEL_FAST handles intake and retries, MODEL_STRONG handles planning and the
document. Check the current official docs for both SDKs before implementing.

The LLM is never the source of truth for any fact that exists in the data.
"""


def chat(messages, tools=None, model=None):
    raise NotImplementedError("Phase 4")
