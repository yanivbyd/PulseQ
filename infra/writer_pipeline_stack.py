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
    article_fn: _lambda.Function,
    quiz_fn: _lambda.Function,
    notification_fn: _lambda.Function,
) -> sfn.StateMachine:
    workflow_end = sfn.Succeed(scope, "WorkflowEnd")

    notification_state = tasks.LambdaInvoke(
        scope,
        "NotificationState",
        lambda_function=notification_fn,
        result_path=sfn.JsonPath.DISCARD,
    )
    notification_state.add_catch(
        handler=workflow_end,
        errors=["States.ALL"],
        result_path=sfn.JsonPath.DISCARD,
    )

    quiz_state = tasks.LambdaInvoke(
        scope,
        "QuizState",
        lambda_function=quiz_fn,
        payload_response_only=True,
    )
    quiz_state.add_retry(
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
    quiz_state.add_catch(
        handler=notification_state,
        errors=["States.ALL"],
        result_path=sfn.JsonPath.DISCARD,
    )

    article_state = tasks.LambdaInvoke(
        scope,
        "ArticleState",
        lambda_function=article_fn,
        payload_response_only=True,
    )
    article_state.add_retry(
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
            article_state.next(quiz_state).next(notification_state).next(workflow_end)
        ),
        state_machine_type=sfn.StateMachineType.EXPRESS,
        timeout=Duration.minutes(5),
        logs=sfn.LogOptions(
            destination=log_group,
            level=sfn.LogLevel.ALL,
            include_execution_data=True,
        ),
    )
