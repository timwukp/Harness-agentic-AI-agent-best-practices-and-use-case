from strands.models.bedrock import BedrockModel


def load_model() -> BedrockModel:
    """Get Bedrock model client using IAM credentials.

    The model is a per-deployment choice — swap in any Bedrock model that fits
    your latency/cost/capability needs. (The live demo Harnesses run
    ``global.anthropic.claude-opus-4-8``; this Runtime-mode default favors
    Sonnet for lower cost.)
    """
    return BedrockModel(model_id="global.anthropic.claude-sonnet-4-5-20250929-v1:0")
