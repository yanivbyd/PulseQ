import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, QueryCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";
import { S3Client, PutObjectCommand, GetObjectCommand } from "@aws-sdk/client-s3";
import type { APIGatewayProxyEventV2, APIGatewayProxyStructuredResultV2 } from "aws-lambda";

function jsonResponse(statusCode: number, body: unknown): APIGatewayProxyStructuredResultV2 {
  return {
    statusCode,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function createHandler(ddbClient: DynamoDBDocumentClient, lambdaClient: LambdaClient, s3Client: S3Client) {
  const tableName = () => {
    const t = process.env.ARTICLES_TABLE;
    if (!t) throw new Error("ARTICLES_TABLE environment variable is not set");
    return t;
  };

  async function handleGenerate(body: string | undefined): Promise<APIGatewayProxyStructuredResultV2> {
    const writerArn = process.env.WRITER_FUNCTION_ARN;
    if (!writerArn) {
      console.error("generate: WRITER_FUNCTION_ARN environment variable is not set");
      return jsonResponse(500, { error: "WRITER_FUNCTION_ARN is not configured" });
    }

    let parsed: unknown;
    try { parsed = JSON.parse(body ?? "{}"); } catch {
      console.warn("generate: invalid JSON body");
      return jsonResponse(400, { error: "Invalid JSON body" });
    }

    const { userId: genUserId } = parsed as Record<string, unknown>;
    if (!genUserId || typeof genUserId !== "string") {
      console.warn(`generate: missing or invalid userId: ${JSON.stringify(genUserId)}`);
      return jsonResponse(400, { error: "userId is required" });
    }

    try {
      await lambdaClient.send(new InvokeCommand({
        FunctionName: writerArn,
        InvocationType: "Event",
        Payload: JSON.stringify({ userId: genUserId }),
      }));
      return jsonResponse(202, { status: "generating" });
    } catch (err) {
      console.error("generate: Lambda invoke failed:", err);
      return jsonResponse(500, { error: "Failed to invoke writer" });
    }
  }

  async function handleScout(body: string | undefined): Promise<APIGatewayProxyStructuredResultV2> {
    const scoutArn = process.env.SCOUT_FUNCTION_ARN;
    if (!scoutArn) {
      console.error("scout: SCOUT_FUNCTION_ARN environment variable is not set");
      return jsonResponse(500, { error: "SCOUT_FUNCTION_ARN is not configured" });
    }

    let parsed: unknown;
    try { parsed = JSON.parse(body ?? "{}"); } catch {
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

  async function handleArticleSummaries(userId: string | undefined): Promise<APIGatewayProxyStructuredResultV2> {
    if (!userId) return jsonResponse(400, { error: "userId query parameter is required" });
    const result = await ddbClient.send(new QueryCommand({
      TableName: tableName(),
      KeyConditionExpression: "userid = :uid",
      FilterExpression: "attribute_not_exists(is_read) OR is_read = :is_read",
      ExpressionAttributeValues: { ":uid": userId, ":is_read": false },
      ScanIndexForward: false,
      Limit: 30,
      ProjectionExpression: "id, title, accent, creation_timestamp, is_read",
    }));
    return jsonResponse(200, result.Items ?? []);
  }

  async function handleArticle(articleId: string): Promise<APIGatewayProxyStructuredResultV2> {
    const result = await ddbClient.send(new QueryCommand({
      TableName: tableName(),
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
    return jsonResponse(200, { id: item.id, title: item.title, accent: item.accent, html: item.html });
  }

  async function handleMarkRead(body: string | undefined): Promise<APIGatewayProxyStructuredResultV2> {
    let parsed: unknown;
    try { parsed = JSON.parse(body ?? "{}"); } catch {
      console.error(`mark-read: invalid JSON body: ${body}`);
      return jsonResponse(400, { error: "Invalid JSON body" });
    }

    const { userId, articleId, is_read, idempotencyKey } = parsed as Record<string, unknown>;
    if (!userId || typeof userId !== "string") {
      console.error(`mark-read: invalid userId: ${JSON.stringify(userId)}`);
      return jsonResponse(400, { error: "userId is required" });
    }
    if (!articleId || typeof articleId !== "string") {
      console.error(`mark-read: invalid articleId: ${JSON.stringify(articleId)}`);
      return jsonResponse(400, { error: "articleId is required" });
    }
    if (typeof is_read !== "boolean") {
      console.error(`mark-read: invalid is_read: ${JSON.stringify(is_read)}`);
      return jsonResponse(400, { error: "is_read must be a boolean" });
    }
    if (!idempotencyKey || typeof idempotencyKey !== "string") {
      console.error(`mark-read: invalid idempotencyKey: ${JSON.stringify(idempotencyKey)}`);
      return jsonResponse(400, { error: "idempotencyKey is required" });
    }

    let articleItem: Record<string, unknown>;
    try {
      const gsiResult = await ddbClient.send(new QueryCommand({
        TableName: tableName(),
        IndexName: "ById",
        KeyConditionExpression: "id = :id",
        ExpressionAttributeValues: { ":id": articleId },
        Limit: 1,
      }));
      if (!gsiResult.Items || gsiResult.Items.length === 0) {
        console.error(`mark-read: article not found: ${articleId}`);
        return jsonResponse(404, { error: "Article not found" });
      }
      articleItem = gsiResult.Items[0];
    } catch (err) {
      console.error(`mark-read: GSI query failed for articleId=${articleId}:`, err);
      return jsonResponse(500, { error: "Failed to look up article" });
    }

    try {
      await ddbClient.send(new UpdateCommand({
        TableName: tableName(),
        Key: { userid: articleItem.userid, creation_timestamp: articleItem.creation_timestamp },
        UpdateExpression: "SET is_read = :is_read",
        ExpressionAttributeValues: { ":is_read": is_read },
      }));
    } catch (err) {
      console.error(`mark-read: UpdateItem failed for articleId=${articleId}:`, err);
      return jsonResponse(500, { error: "Failed to update article" });
    }

    console.log(`mark-read: set articleId=${articleId} is_read=${is_read} for userId=${userId}`);
    return jsonResponse(200, {});
  }

  async function handleTopics(userId: string | undefined): Promise<APIGatewayProxyStructuredResultV2> {
    if (!userId) {
      console.error("topics: userId is required");
      return jsonResponse(400, { error: "userId is required" });
    }
    const bucket = process.env.INPUT_BUCKET;
    if (!bucket) {
      console.error("topics: INPUT_BUCKET environment variable is not set");
      return jsonResponse(500, { error: "INPUT_BUCKET is not configured" });
    }
    try {
      const result = await s3Client.send(new GetObjectCommand({ Bucket: bucket, Key: `${userId}/topics.json` }));
      const body = await result.Body?.transformToString();
      const data = JSON.parse(body ?? "{}") as { topics?: Array<{ title: string; description: string }> };
      return jsonResponse(200, { topics: data.topics ?? [] });
    } catch (err: unknown) {
      if ((err as { name?: string }).name === "NoSuchKey") {
        console.warn(`topics: no topics file found for userId=${userId}`);
        return jsonResponse(200, { topics: [] });
      }
      console.error(`topics: S3 read failed for userId=${userId}:`, err);
      return jsonResponse(500, { error: "Failed to read topics" });
    }
  }

  async function handleFeedback(body: string | undefined): Promise<APIGatewayProxyStructuredResultV2> {
    const bucket = process.env.EVENTS_BUCKET;
    if (!bucket) {
      console.error("feedback: EVENTS_BUCKET environment variable is not set");
      return jsonResponse(500, { error: "EVENTS_BUCKET is not configured" });
    }

    let parsed: unknown;
    try { parsed = JSON.parse(body ?? "{}"); } catch {
      console.warn(`feedback: invalid JSON body: ${body}`);
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
    } catch (err) {
      console.error(`feedback: S3 write failed for key ${key}:`, err);
      return jsonResponse(500, { error: "Failed to write feedback" });
    }

    async function markArticleRead(id: string) {
      const gsiResult = await ddbClient.send(new QueryCommand({
        TableName: tableName(),
        IndexName: "ById",
        KeyConditionExpression: "id = :id",
        ExpressionAttributeValues: { ":id": id },
        Limit: 1,
      }));
      if (gsiResult.Items && gsiResult.Items.length > 0) {
        const item = gsiResult.Items[0];
        await ddbClient.send(new UpdateCommand({
          TableName: tableName(),
          Key: { userid: item.userid, creation_timestamp: item.creation_timestamp },
          UpdateExpression: "SET is_read = :true",
          ExpressionAttributeValues: { ":true": true },
        }));
        console.info(`feedback: marked article ${id} as read`);
      }
    }

    // Best-effort: mark article as read after feedback
    try {
      await markArticleRead(articleId);
    } catch (err) {
      console.warn(`feedback: failed to mark article ${articleId} as read:`, err);
    }

    return jsonResponse(200, {});
  }

  return async function (event: APIGatewayProxyEventV2): Promise<APIGatewayProxyStructuredResultV2> {
    tableName(); // validate env var eagerly

    const path = event.rawPath ?? "";
    const method = event.requestContext?.http?.method;

    if (path === "/api/topics" && method === "GET") return handleTopics(event.queryStringParameters?.userId);
    if (path === "/api/generate" && method === "POST") return handleGenerate(event.body);
    if (path === "/api/scout" && method === "POST") return handleScout(event.body);
    if (path === "/api/article-summaries") return handleArticleSummaries(event.queryStringParameters?.userId);
    if (path === "/api/mark-read" && method === "POST") return handleMarkRead(event.body);
    if (path === "/api/feedback" && method === "POST") return handleFeedback(event.body);

    const articleId = path.startsWith("/api/article/") ? path.split("/")[3] : undefined;
    if (articleId) return handleArticle(articleId);

    console.warn(`router: no route matched: ${method} ${path}`);
    return jsonResponse(404, { error: "Not Found" });
  };
}

const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({ region: "eu-west-1" }));
const lambda = new LambdaClient({ region: "eu-west-1" });
const s3 = new S3Client({ region: "eu-west-1" });
export const handler = createHandler(ddb, lambda, s3);
