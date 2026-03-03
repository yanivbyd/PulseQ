import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, QueryCommand } from "@aws-sdk/lib-dynamodb";
import type { APIGatewayProxyEventV2, APIGatewayProxyStructuredResultV2 } from "aws-lambda";

const CSS_URL = "https://d1vjqvihd6azy3.cloudfront.net/style.css?v=2";
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

export function buildHomeFragment(items: Record<string, unknown>[]): string {
  const cards = items.length === 0
    ? "<p>No articles yet.</p>"
    : items.map(item =>
        `<a href="/${item.id}" class="home-item" style="background:${item.accent}"><span class="home-title">${item.title}</span></a>`
      ).join("\n");
  return `<article>\n<div class="header-card"><h1>PulseQ</h1></div>\n<div class="section home-list">\n${cards}\n</div>\n</article>`;
}

export function createHandler(ddbClient: DynamoDBDocumentClient) {
  return async function (event: APIGatewayProxyEventV2): Promise<APIGatewayProxyStructuredResultV2> {
    const tableName = process.env.ARTICLES_TABLE;
    if (!tableName) throw new Error("ARTICLES_TABLE environment variable is not set");

    const id = event.pathParameters?.id;

    if (!id) {
      const result = await ddbClient.send(new QueryCommand({
        TableName: tableName,
        KeyConditionExpression: "userid = :uid",
        ExpressionAttributeValues: { ":uid": USER_ID },
        ScanIndexForward: false,
        Limit: 30,
      }));
      return {
        statusCode: 200,
        headers: { "Content-Type": "text/html; charset=utf-8" },
        body: buildShell("PulseQ", buildHomeFragment(result.Items ?? [])),
      };
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
