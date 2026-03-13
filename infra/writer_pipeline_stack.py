from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
)
from constructs import Construct


def create_writer_pipeline(
    scope: Construct,
    topic_selector_fn: _lambda.Function,
    tavily_fn: _lambda.Function,
    article_fn: _lambda.Function,
    quiz_fn: _lambda.Function,
    notification_fn: _lambda.Function,
) -> sfn.StateMachine:
    workflow_end = sfn.Succeed(scope, "WorkflowEnd")
    workflow_fail = sfn.Fail(scope, "WorkflowFail", cause="Pipeline step failed")

    notification = tasks.LambdaInvoke(
        scope,
        "Notification",
        lambda_function=notification_fn,
        result_path=sfn.JsonPath.DISCARD,
    )
    notification.add_catch(
        handler=workflow_end,
        errors=["States.ALL"],
        result_path=sfn.JsonPath.DISCARD,
    )

    quiz = tasks.LambdaInvoke(
        scope,
        "Quiz",
        lambda_function=quiz_fn,
        payload_response_only=True,
    )
    quiz.add_retry(
        errors=[
            "Lambda.ServiceException",
            "Lambda.AWSLambdaException",
            "Lambda.SdkClientException",
            "Lambda.TooManyRequestsException",
        ],
        max_attempts=2,
        backoff_rate=2,
        interval=Duration.seconds(1),
    )
    quiz.add_catch(
        handler=notification,
        errors=["States.ALL"],
        result_path=sfn.JsonPath.DISCARD,
    )

    article = tasks.LambdaInvoke(
        scope,
        "Article",
        lambda_function=article_fn,
        payload_response_only=True,
    )
    article.add_retry(
        errors=[
            "Lambda.ServiceException",
            "Lambda.AWSLambdaException",
            "Lambda.SdkClientException",
            "Lambda.TooManyRequestsException",
        ],
        max_attempts=2,
        backoff_rate=2,
        interval=Duration.seconds(1),
    )

    tavily = tasks.LambdaInvoke(
        scope,
        "Tavily",
        lambda_function=tavily_fn,
        payload_response_only=True,
    )
    tavily.add_retry(
        errors=[
            "Lambda.ServiceException",
            "Lambda.AWSLambdaException",
            "Lambda.SdkClientException",
            "Lambda.TooManyRequestsException",
        ],
        max_attempts=2,
        backoff_rate=2,
        interval=Duration.seconds(1),
    )
    tavily.add_catch(
        handler=article,
        errors=["States.ALL"],
        result_path=sfn.JsonPath.DISCARD,
    )

    topic_selector = tasks.LambdaInvoke(
        scope,
        "TopicSelector",
        lambda_function=topic_selector_fn,
        payload_response_only=True,
    )
    topic_selector.add_retry(
        errors=[
            "Lambda.ServiceException",
            "Lambda.AWSLambdaException",
            "Lambda.SdkClientException",
            "Lambda.TooManyRequestsException",
        ],
        max_attempts=2,
        backoff_rate=2,
        interval=Duration.seconds(1),
    )
    topic_selector.add_catch(
        handler=workflow_fail,
        errors=["States.ALL"],
        result_path=sfn.JsonPath.DISCARD,
    )

    log_group = logs.LogGroup(
        scope,
        "WriterStateMachineLogs",
        log_group_name="/aws/states/WriterStateMachine",
        retention=logs.RetentionDays.ONE_WEEK,
        removal_policy=RemovalPolicy.DESTROY,
    )

    return sfn.StateMachine(
        scope,
        "WriterStateMachine",
        state_machine_name="article-generation",
        definition_body=sfn.DefinitionBody.from_chainable(
            topic_selector.next(tavily).next(article).next(quiz).next(notification).next(workflow_end)
        ),
        state_machine_type=sfn.StateMachineType.EXPRESS,
        timeout=Duration.minutes(5),
        logs=sfn.LogOptions(
            destination=log_group,
            level=sfn.LogLevel.ALL,
            include_execution_data=True,
        ),
    )
