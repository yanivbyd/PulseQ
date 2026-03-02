import os

import aws_cdk as cdk
from stack import WriterStack

app = cdk.App()
WriterStack(
    app,
    "WriterStack",
    env=cdk.Environment(
        account=os.environ["CDK_DEFAULT_ACCOUNT"],
        region=os.environ.get("CDK_DEFAULT_REGION", "eu-west-1"),
    ),
)
app.synth()
