import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, QueryCommand } from "@aws-sdk/lib-dynamodb";
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";
import type { APIGatewayProxyEventV2, APIGatewayProxyStructuredResultV2 } from "aws-lambda";

function jsonResponse(statusCode: number, body: unknown): APIGatewayProxyStructuredResultV2 {
  return {
    statusCode,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function createHandler(ddbClient: DynamoDBDocumentClient, lambdaClient: LambdaClient) {
  return async function (event: APIGatewayProxyEventV2): Promise<APIGatewayProxyStructuredResultV2> {
    const tableName = process.env.ARTICLES_TABLE;
    if (!tableName) throw new Error("ARTICLES_TABLE environment variable is not set");

    const path = event.rawPath ?? "";
    const method = event.requestContext?.http?.method;

    if (path === "/api/generate" && method === "POST") {
      const writerArn = process.env.WRITER_FUNCTION_ARN;
      if (!writerArn) return jsonResponse(500, { error: "WRITER_FUNCTION_ARN is not configured" });
      try {
        await lambdaClient.send(new InvokeCommand({
          FunctionName: writerArn,
          InvocationType: "Event",
        }));
        return jsonResponse(202, { status: "generating" });
      } catch {
        return jsonResponse(500, { error: "Failed to invoke writer" });
      }
    }

    if (path === "/api/article-summaries") {
      const userId = event.queryStringParameters?.userId;
      if (!userId) return jsonResponse(400, { error: "userId query parameter is required" });
      const result = await ddbClient.send(new QueryCommand({
        TableName: tableName,
        KeyConditionExpression: "userid = :uid",
        ExpressionAttributeValues: { ":uid": userId },
        ScanIndexForward: false,
        Limit: 30,
        ProjectionExpression: "id, title, accent, creation_timestamp",
      }));
      return jsonResponse(200, result.Items ?? []);
    }

    const articleId = path.startsWith("/api/article/") ? path.split("/")[3] : undefined;
    if (articleId) {
      const result = await ddbClient.send(new QueryCommand({
        TableName: tableName,
        IndexName: "ById",
        KeyConditionExpression: "id = :id",
        ExpressionAttributeValues: { ":id": articleId },
        Limit: 1,
      }));

      if (!result.Items || result.Items.length === 0) {
        return jsonResponse(404, { error: "Not Found" });
      }

      const item = result.Items[0];
      return jsonResponse(200, {
        id: item.id,
        title: item.title,
        accent: item.accent,
        html: item.html,
      });
    }

    return jsonResponse(404, { error: "Not Found" });
  };
}

const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({ region: "eu-west-1" }));
const lambda = new LambdaClient({ region: "eu-west-1" });
export const handler = createHandler(ddb, lambda);
