import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, QueryCommand } from "@aws-sdk/lib-dynamodb";
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import type { APIGatewayProxyEventV2, APIGatewayProxyStructuredResultV2 } from "aws-lambda";

function jsonResponse(statusCode: number, body: unknown): APIGatewayProxyStructuredResultV2 {
  return {
    statusCode,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function createHandler(ddbClient: DynamoDBDocumentClient, lambdaClient: LambdaClient, s3Client: S3Client) {
  return async function (event: APIGatewayProxyEventV2): Promise<APIGatewayProxyStructuredResultV2> {
    const tableName = process.env.ARTICLES_TABLE;
    if (!tableName) throw new Error("ARTICLES_TABLE environment variable is not set");

    const path = event.rawPath ?? "";
    const method = event.requestContext?.http?.method;

    if (path === "/api/generate" && method === "POST") {
      const writerArn = process.env.WRITER_FUNCTION_ARN;
      if (!writerArn) {
        console.error("generate: WRITER_FUNCTION_ARN environment variable is not set");
        return jsonResponse(500, { error: "WRITER_FUNCTION_ARN is not configured" });
      }
      try {
        await lambdaClient.send(new InvokeCommand({
          FunctionName: writerArn,
          InvocationType: "Event",
        }));
        return jsonResponse(202, { status: "generating" });
      } catch (err) {
        console.error("generate: Lambda invoke failed:", err);
        return jsonResponse(500, { error: "Failed to invoke writer" });
      }
    }

    if (path === "/api/scout" && method === "POST") {
      const scoutArn = process.env.SCOUT_FUNCTION_ARN;
      if (!scoutArn) {
        console.error("scout: SCOUT_FUNCTION_ARN environment variable is not set");
        return jsonResponse(500, { error: "SCOUT_FUNCTION_ARN is not configured" });
      }

      let parsed: unknown;
      try { parsed = JSON.parse(event.body ?? "{}"); } catch {
        console.warn("scout: invalid JSON body");
        return jsonResponse(400, { error: "Invalid JSON body" });
      }

      const { userId } = parsed as Record<string, unknown>;
      if (!userId || typeof userId !== "string") {
        console.warn(`scout: missing or invalid userId: ${JSON.stringify(userId)}`);
        return jsonResponse(400, { error: "userId is required" });
      }

      try {
        await lambdaClient.send(new InvokeCommand({
          FunctionName: scoutArn,
          InvocationType: "Event",
          Payload: JSON.stringify({ userId }),
        }));
        return jsonResponse(202, { status: "scouting" });
      } catch (err) {
        console.error("scout: Lambda invoke failed:", err);
        return jsonResponse(500, { error: "Failed to invoke scout" });
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
        console.warn(`article: not found: ${articleId}`);
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

    if (path === "/api/feedback" && method === "POST") {
      const bucket = process.env.EVENTS_BUCKET;
      if (!bucket) {
        console.error("feedback: EVENTS_BUCKET environment variable is not set");
        return jsonResponse(500, { error: "EVENTS_BUCKET is not configured" });
      }

      let parsed: unknown;
      try { parsed = JSON.parse(event.body ?? "{}"); } catch {
        console.warn(`feedback: invalid JSON body: ${event.body}`);
        return jsonResponse(400, { error: "Invalid JSON body" });
      }

      const { articleId, userId, reaction, clientTimestamp, articleTitle } = parsed as Record<string, unknown>;
      if (!articleId || typeof articleId !== "string") {
        console.warn(`feedback: invalid articleId: ${JSON.stringify(articleId)}`);
        return jsonResponse(400, { error: "articleId is required" });
      }
      if (!userId || typeof userId !== "string") {
        console.warn(`feedback: invalid userId: ${JSON.stringify(userId)}`);
        return jsonResponse(400, { error: "userId is required" });
      }
      if (!articleTitle || typeof articleTitle !== "string") {
        console.warn(`feedback: invalid articleTitle: ${JSON.stringify(articleTitle)}`);
        return jsonResponse(400, { error: "articleTitle is required" });
      }
      if (reaction !== "like" && reaction !== "dislike") {
        console.warn(`feedback: invalid reaction: ${JSON.stringify(reaction)}`);
        return jsonResponse(400, { error: "reaction must be like or dislike" });
      }
      if (!clientTimestamp || typeof clientTimestamp !== "string") {
        console.warn(`feedback: invalid clientTimestamp: ${JSON.stringify(clientTimestamp)}`);
        return jsonResponse(400, { error: "clientTimestamp is required" });
      }

      // Sanitised format: YYYY-MM-DDTHH-MM-SS.mmmZ — restore colons in the time part to parse as ISO 8601
      const tIdx = clientTimestamp.indexOf("T");
      if (tIdx === -1) {
        console.warn(`feedback: clientTimestamp missing T separator: ${clientTimestamp}`);
        return jsonResponse(400, { error: "invalid clientTimestamp" });
      }
      const iso = clientTimestamp.slice(0, tIdx + 1) + clientTimestamp.slice(tIdx + 1).replace(/-/g, ":");
      const ts = new Date(iso);
      if (isNaN(ts.getTime())) {
        console.warn(`feedback: unparseable clientTimestamp: ${clientTimestamp}`);
        return jsonResponse(400, { error: "invalid clientTimestamp" });
      }
      if (Math.abs(Date.now() - ts.getTime()) > 15 * 60 * 1000) {
        console.warn(`feedback: clientTimestamp out of range: ${clientTimestamp} (server: ${new Date().toISOString()}, diff: ${Math.round((Date.now() - ts.getTime()) / 1000)}s)`);
        return jsonResponse(400, { error: "clientTimestamp is too far from server time" });
      }

      const key = `${userId}/${clientTimestamp}_article_${articleId}_general_feedback.json`;
      try {
        await s3Client.send(new PutObjectCommand({
          Bucket: bucket,
          Key: key,
          Body: JSON.stringify({ articleId, articleTitle, userId, reaction, clientTimestamp }),
          ContentType: "application/json",
        }));
        return jsonResponse(200, {});
      } catch (err) {
        console.error(`feedback: S3 write failed for key ${key}:`, err);
        return jsonResponse(500, { error: "Failed to write feedback" });
      }
    }

    console.warn(`router: no route matched: ${method} ${path}`);
    return jsonResponse(404, { error: "Not Found" });
  };
}

const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({ region: "eu-west-1" }));
const lambda = new LambdaClient({ region: "eu-west-1" });
const s3 = new S3Client({ region: "eu-west-1" });
export const handler = createHandler(ddb, lambda, s3);
