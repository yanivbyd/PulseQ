from dataclasses import dataclass

from aws_cdk import aws_secretsmanager as sm
from constructs import Construct


@dataclass
class Secrets:
    openai: sm.ISecret
    ifttt: sm.ISecret
    tavily: sm.ISecret


def create_secrets(scope: Construct) -> Secrets:
    openai = sm.Secret(
        scope,
        "OpenAIApiKey",
        secret_name="pulseq/openai-api-key",
        description="OpenAI API key",
    )

    ifttt = sm.Secret.from_secret_name_v2(
        scope,
        "IftttKey",
        "pulseq/ifttt-key",
    )

    tavily = sm.Secret(
        scope,
        "TavilyApiKey",
        secret_name="pulseq/tavily-api-key",
        description="Tavily API key",
    )

    return Secrets(openai=openai, ifttt=ifttt, tavily=tavily)
