import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, DeleteCommand, GetCommand, QueryCommand } from "@aws-sdk/lib-dynamodb";
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";
import { SFNClient, StartExecutionCommand } from "@aws-sdk/client-sfn";
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import type { APIGatewayProxyEventV2, APIGatewayProxyStructuredResultV2 } from "aws-lambda";
import type { WorkflowInputState } from "./workflow_input_state";

function jsonResponse(statusCode: number, body: unknown): APIGatewayProxyStructuredResultV2 {
  return {
    statusCode,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function createHandler(ddbClient: DynamoDBDocumentClient, lambdaClient: LambdaClient, s3Client: S3Client, sfnClient: SFNClient) {
  const articlesTable = () => {
    const t = process.env.ARTICLES_TABLE;
    if (!t) throw new Error("ARTICLES_TABLE environment variable is not set");
    return t;
  };

  const inboxTable = () => {
    const t = process.env.USER_INBOX_TABLE;
    if (!t) throw new Error("USER_INBOX_TABLE environment variable is not set");
    return t;
  };

  async function handleGenerate(body: string | undefined): Promise<APIGatewayProxyStructuredResultV2> {
    const stateMachineArn = process.env.WRITER_STATE_MACHINE_ARN;
    if (!stateMachineArn) {
      console.error("generate: WRITER_STATE_MACHINE_ARN environment variable is not set");
      return jsonResponse(500, { error: "WRITER_STATE_MACHINE_ARN is not configured" });
    }

    let parsed: unknown;
    try { parsed = JSON.parse(body ?? "{}"); } catch {
      console.warn("generate: invalid JSON body");
      return jsonResponse(400, { error: "Invalid JSON body" });
    }

    const { userId: genUserId, customTopic, followUpArticleId, followUpExtraContext } = parsed as Record<string, unknown>;
    if (!genUserId || typeof genUserId !== "string") {
      console.warn(`generate: missing or invalid userId: ${JSON.stringify(genUserId)}`);
      return jsonResponse(400, { error: "userId is required" });
    }
    if (customTopic !== undefined) {
      if (typeof customTopic !== "string" || customTopic.length > 1000) {
        console.warn(`generate: customTopic invalid or too long: length=${typeof customTopic === "string" ? customTopic.length : typeof customTopic}`);
        return jsonResponse(400, { error: "customTopic must be a string of at most 1000 characters" });
      }
    }
    if (customTopic !== undefined && followUpArticleId !== undefined) {
      console.warn("generate: customTopic and followUpArticleId are mutually exclusive");
      return jsonResponse(400, { error: "customTopic and followUpArticleId are mutually exclusive" });
    }
    if (followUpArticleId !== undefined) {
      if (typeof followUpArticleId !== "string" || !followUpArticleId) {
        console.warn(`generate: followUpArticleId invalid: ${JSON.stringify(followUpArticleId)}`);
        return jsonResponse(400, { error: "followUpArticleId must be a non-empty string" });
      }
      if (!followUpExtraContext || typeof followUpExtraContext !== "string" || (followUpExtraContext as string).length > 1000) {
        console.warn(`generate: followUpExtraContext invalid: ${JSON.stringify(followUpExtraContext)}`);
        return jsonResponse(400, { error: "followUpExtraContext must be a non-empty string of at most 1000 characters" });
      }
    }

    const sfnInput: WorkflowInputState = { userId: genUserId };
    if (customTopic !== undefined) sfnInput.customTopic = customTopic as string;
    if (followUpArticleId !== undefined) {
      sfnInput.followUpArticleId = followUpArticleId as string;
      sfnInput.extraContent = followUpExtraContext as string;
    }

    try {
      await sfnClient.send(new StartExecutionCommand({
        stateMachineArn,
        input: JSON.stringify(sfnInput),
      }));
      return jsonResponse(202, { status: "generating" });
    } catch (err) {
      console.error("generate: StartExecution failed:", err);
      return jsonResponse(500, { error: "Failed to start writer pipeline" });
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
      TableName: inboxTable(),
      KeyConditionExpression: "userId = :uid",
      ExpressionAttributeValues: { ":uid": userId },
      ScanIndexForward: false,
    }));
    return jsonResponse(200, result.Items ?? []);
  }

  async function handleArticle(articleId: string): Promise<APIGatewayProxyStructuredResultV2> {
    const result = await ddbClient.send(new GetCommand({
      TableName: articlesTable(),
      Key: { articleId },
    }));

    if (!result.Item) {
      console.warn(`article: not found: ${articleId}`);
      return jsonResponse(404, { error: "Not Found" });
    }

    const item = result.Item;
    let quiz: unknown[] = [];
    if (typeof item.quiz === "string") {
      try {
        const parsed = JSON.parse(item.quiz);
        if (Array.isArray(parsed)) quiz = parsed;
        else console.warn(`article: quiz field is not an array for articleId=${articleId}`);
      } catch {
        console.warn(`article: invalid quiz JSON for articleId=${articleId}`);
      }
    }
    let further_reading: unknown[] = [];
    if (typeof item.further_reading === "string") {
      try {
        const parsed = JSON.parse(item.further_reading);
        if (Array.isArray(parsed)) further_reading = parsed;
        else console.warn(`article: further_reading field is not an array for articleId=${articleId}`);
      } catch {
        console.warn(`article: invalid further_reading JSON for articleId=${articleId}`);
      }
    }
    return jsonResponse(200, { articleId: item.articleId, title: item.title, html: item.html, quiz, further_reading });
  }

  async function handleMarkRead(body: string | undefined): Promise<APIGatewayProxyStructuredResultV2> {
    let parsed: unknown;
    try { parsed = JSON.parse(body ?? "{}"); } catch {
      console.error(`mark-read: invalid JSON body: ${body}`);
      return jsonResponse(400, { error: "Invalid JSON body" });
    }

    const { userId, articleId } = parsed as Record<string, unknown>;
    if (!userId || typeof userId !== "string") {
      console.error(`mark-read: invalid userId: ${JSON.stringify(userId)}`);
      return jsonResponse(400, { error: "userId is required" });
    }
    if (!articleId || typeof articleId !== "string") {
      console.error(`mark-read: invalid articleId: ${JSON.stringify(articleId)}`);
      return jsonResponse(400, { error: "articleId is required" });
    }

    try {
      await ddbClient.send(new DeleteCommand({
        TableName: inboxTable(),
        Key: { userId, articleId },
      }));
    } catch (err) {
      console.error(`mark-read: DeleteItem failed for articleId=${articleId}:`, err);
      return jsonResponse(500, { error: "Failed to mark article as read" });
    }

    console.log(`mark-read: deleted articleId=${articleId} from inbox for userId=${userId}`);
    return jsonResponse(200, {});
  }

  async function handleTopics(userId: string | undefined): Promise<APIGatewayProxyStructuredResultV2> {
    if (!userId) {
      console.error("topics: userId is required");
      return jsonResponse(400, { error: "userId is required" });
    }
    const topicsTable = process.env.TOPICS_TABLE;
    if (!topicsTable) {
      console.error("topics: TOPICS_TABLE environment variable is not set");
      return jsonResponse(500, { error: "TOPICS_TABLE is not configured" });
    }
    try {
      const result = await ddbClient.send(new GetCommand({ TableName: topicsTable, Key: { userId } }));
      const topics = (result.Item?.topics as Array<{ title: string; description: string }>) ?? [];
      return jsonResponse(200, { topics });
    } catch (err) {
      console.error(`topics: DDB read failed for userId=${userId}:`, err);
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

    const { articleId, userId, content, clientTimestamp, articleTitle } = parsed as Record<string, unknown>;
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
    if (!clientTimestamp || typeof clientTimestamp !== "string") {
      console.warn(`feedback: invalid clientTimestamp: ${JSON.stringify(clientTimestamp)}`);
      return jsonResponse(400, { error: "clientTimestamp is required" });
    }
    if (!content || typeof content !== "object" || Array.isArray(content)) {
      console.warn(`feedback: invalid content: ${JSON.stringify(content)}`);
      return jsonResponse(400, { error: "content must be an object" });
    }
    const contentObj = content as Record<string, unknown>;
    if (contentObj.type !== "reaction" && contentObj.type !== "freeText") {
      console.warn(`feedback: invalid content.type: ${JSON.stringify(contentObj.type)}`);
      return jsonResponse(400, { error: "content.type must be reaction or freeText" });
    }
    if (contentObj.type === "reaction" && contentObj.reaction !== "like" && contentObj.reaction !== "dislike") {
      console.warn(`feedback: invalid content.reaction: ${JSON.stringify(contentObj.reaction)}`);
      return jsonResponse(400, { error: "content.reaction must be like or dislike" });
    }
    if (contentObj.type === "freeText" && (typeof contentObj.text !== "string" || contentObj.text.length > 5000)) {
      console.warn(`feedback: invalid content.text: ${JSON.stringify(contentObj.text)}`);
      return jsonResponse(400, { error: "content.text must be a string with length <= 5000" });
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

    const key = `${userId}/${clientTimestamp}_article_${articleId}_feedback.json`;
    try {
      await s3Client.send(new PutObjectCommand({
        Bucket: bucket,
        Key: key,
        Body: JSON.stringify({ articleId, articleTitle, userId, clientTimestamp, content }),
        ContentType: "application/json",
      }));
    } catch (err) {
      console.error(`feedback: S3 write failed for key ${key}:`, err);
      return jsonResponse(500, { error: "Failed to write feedback" });
    }

    // Best-effort: remove article from inbox after any feedback
    try {
      await ddbClient.send(new DeleteCommand({
        TableName: inboxTable(),
        Key: { userId: userId as string, articleId: articleId as string },
      }));
      console.info(`feedback: removed articleId=${articleId} from inbox for userId=${userId}`);
    } catch (err) {
      console.warn(`feedback: failed to remove article ${articleId} from inbox:`, err);
    }

    return jsonResponse(200, {});
  }

  return async function (event: APIGatewayProxyEventV2): Promise<APIGatewayProxyStructuredResultV2> {
    articlesTable(); // validate env var eagerly
    inboxTable();    // validate env var eagerly

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
const sfn = new SFNClient({ region: "eu-west-1" });
export const handler = createHandler(ddb, lambda, s3, sfn);
