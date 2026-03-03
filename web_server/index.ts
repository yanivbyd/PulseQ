import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, QueryCommand } from "@aws-sdk/lib-dynamodb";
import type { APIGatewayProxyEventV2, APIGatewayProxyStructuredResultV2 } from "aws-lambda";

const CSS_URL = "https://d1vjqvihd6azy3.cloudfront.net/style.css";
const USER_ID = "user1";

export function buildShell(title: string, fragment: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  <link rel="stylesheet" href="${CSS_URL}">
</head>
<body>
${fragment}
</body>
</html>`;
}

export function createHandler(ddbClient: DynamoDBDocumentClient) {
  return async function (event: APIGatewayProxyEventV2): Promise<APIGatewayProxyStructuredResultV2> {
    const tableName = process.env.ARTICLES_TABLE;
    if (!tableName) throw new Error("ARTICLES_TABLE environment variable is not set");

    const id = event.pathParameters?.id;
    if (!id) {
      return { statusCode: 404, body: "Not Found" };
    }

    const result = await ddbClient.send(new QueryCommand({
      TableName: tableName,
      IndexName: "ById",
      KeyConditionExpression: "id = :id",
      ExpressionAttributeValues: { ":id": id },
      Limit: 1,
    }));

    if (!result.Items || result.Items.length === 0) {
      return { statusCode: 404, body: "Not Found" };
    }

    const item = result.Items[0];
    return {
      statusCode: 200,
      headers: { "Content-Type": "text/html; charset=utf-8" },
      body: buildShell(item.title as string, item.html as string),
    };
  };
}

const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({ region: "eu-west-1" }));
export const handler = createHandler(ddb);
