import { createHandler } from "../index";
import { DynamoDBDocumentClient, QueryCommand } from "@aws-sdk/lib-dynamodb";
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";
import type { APIGatewayProxyEventV2, APIGatewayProxyStructuredResultV2 } from "aws-lambda";

function makeGatewayEvent(
  rawPath: string,
  queryParams?: Record<string, string>,
  method = "GET",
): APIGatewayProxyEventV2 {
  return {
    rawPath,
    queryStringParameters: queryParams,
    requestContext: { http: { method } },
  } as unknown as APIGatewayProxyEventV2;
}

// Routes main-table queries to the matching userId bucket; searches all items for ById GSI queries.
function makeMockDdb(db: Record<string, Record<string, unknown>[]>) {
  const send = jest.fn().mockImplementation((cmd: QueryCommand) => {
    const uid = cmd.input.ExpressionAttributeValues?.[":uid"] as string | undefined;
    const id  = cmd.input.ExpressionAttributeValues?.[":id"]  as string | undefined;
    if (uid !== undefined) {
      return Promise.resolve({ Items: db[uid] ?? [] });
    }
    if (id !== undefined) {
      const found = Object.values(db).flat().find((item) => item.id === id);
      return Promise.resolve({ Items: found ? [found] : [] });
    }
    return Promise.resolve({ Items: [] });
  });
  return { send } as unknown as DynamoDBDocumentClient;
}

function makeMockDdbThrowing() {
  const send = jest.fn().mockRejectedValue(new Error("DynamoDB error"));
  return { send } as unknown as DynamoDBDocumentClient;
}

function makeMockLambda(shouldFail = false) {
  const send = jest.fn().mockImplementation(() =>
    shouldFail
      ? Promise.reject(new Error("Lambda error"))
      : Promise.resolve({}),
  );
  return { send } as unknown as LambdaClient;
}

const SAMPLE_ARTICLE = {
  id: "abc12",
  title: "How Load Balancers Work",
  accent: "#0d9488",
  creation_timestamp: "2026-03-03T14:00:00.000Z",
  userid: "user1",
  html: '<div class="header-card"><h1>How Load Balancers Work</h1></div>',
};

const SAMPLE_ARTICLE_2 = {
  id: "xyz99",
  title: "Docker Internals",
  accent: "#7c3aed",
  creation_timestamp: "2026-03-02T10:00:00.000Z",
  userid: "userX",
  html: '<div class="header-card"><h1>Docker Internals</h1></div>',
};

const MOCK_DB: Record<string, Record<string, unknown>[]> = {
  user1: [SAMPLE_ARTICLE],
  userX: [SAMPLE_ARTICLE_2],
};

const mockLambda = makeMockLambda();

describe("GET /api/article-summaries", () => {
  beforeEach(() => { process.env.ARTICLES_TABLE = "pulseq-articles"; });

  test("returns 200 JSON for user1", async () => {
    const result = await createHandler(makeMockDdb(MOCK_DB), mockLambda)(
      makeGatewayEvent("/api/article-summaries", { userId: "user1" }),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
    expect(result.headers!["Content-Type"]).toBe("application/json");
    const body = JSON.parse(result.body as string);
    expect(body).toHaveLength(1);
    expect(body[0]).toMatchObject({ id: "abc12", title: "How Load Balancers Work" });
  });

  test("returns only userX's articles, not user1's", async () => {
    const result = await createHandler(makeMockDdb(MOCK_DB), mockLambda)(
      makeGatewayEvent("/api/article-summaries", { userId: "userX" }),
    ) as APIGatewayProxyStructuredResultV2;
    const body = JSON.parse(result.body as string);
    expect(body).toHaveLength(1);
    expect(body[0]).toMatchObject({ id: "xyz99", title: "Docker Internals" });
  });

  test("returns 400 when userId is not provided", async () => {
    const result = await createHandler(makeMockDdb(MOCK_DB), mockLambda)(
      makeGatewayEvent("/api/article-summaries"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string)).toMatchObject({ error: expect.stringContaining("userId") });
  });

  test("queries with ProjectionExpression that excludes html", async () => {
    const ddb = makeMockDdb(MOCK_DB);
    await createHandler(ddb, mockLambda)(makeGatewayEvent("/api/article-summaries", { userId: "user1" }));
    const cmd = (ddb.send as jest.Mock).mock.calls[0][0] as QueryCommand;
    expect(cmd.input.ProjectionExpression).toBeDefined();
    expect(cmd.input.ProjectionExpression).not.toContain("html");
  });

  test("returns empty array for unknown userId", async () => {
    const result = await createHandler(makeMockDdb(MOCK_DB), mockLambda)(
      makeGatewayEvent("/api/article-summaries", { userId: "nobody" }),
    ) as APIGatewayProxyStructuredResultV2;
    expect(JSON.parse(result.body as string)).toEqual([]);
  });

  test("propagates DynamoDB errors", async () => {
    await expect(
      createHandler(makeMockDdbThrowing(), mockLambda)(makeGatewayEvent("/api/article-summaries", { userId: "user1" })),
    ).rejects.toThrow();
  });
});

describe("GET /api/article/:articleId", () => {
  beforeEach(() => { process.env.ARTICLES_TABLE = "pulseq-articles"; });

  test("returns full article JSON", async () => {
    const result = await createHandler(makeMockDdb(MOCK_DB), mockLambda)(
      makeGatewayEvent("/api/article/abc12"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
    expect(result.headers!["Content-Type"]).toBe("application/json");
    const body = JSON.parse(result.body as string);
    expect(body.id).toBe("abc12");
    expect(body.title).toBe("How Load Balancers Work");
    expect(body.html).toBe(SAMPLE_ARTICLE.html);
    expect(body.userid).toBeUndefined(); // internal field not exposed
  });

  test("queries ById GSI with the articleId", async () => {
    const ddb = makeMockDdb(MOCK_DB);
    await createHandler(ddb, mockLambda)(makeGatewayEvent("/api/article/abc12"));
    const cmd = (ddb.send as jest.Mock).mock.calls[0][0] as QueryCommand;
    expect(cmd.input.IndexName).toBe("ById");
    expect(cmd.input.ExpressionAttributeValues).toMatchObject({ ":id": "abc12" });
  });

  test("returns 404 when article not found", async () => {
    const result = await createHandler(makeMockDdb(MOCK_DB), mockLambda)(
      makeGatewayEvent("/api/article/missing"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(404);
  });

  test("propagates DynamoDB errors", async () => {
    await expect(
      createHandler(makeMockDdbThrowing(), mockLambda)(makeGatewayEvent("/api/article/abc12")),
    ).rejects.toThrow();
  });
});

describe("unknown paths", () => {
  beforeEach(() => { process.env.ARTICLES_TABLE = "pulseq-articles"; });

  test("returns 404 JSON for unknown routes", async () => {
    const result = await createHandler(makeMockDdb({}), mockLambda)(makeGatewayEvent("/unknown")) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(404);
    expect(result.headers!["Content-Type"]).toBe("application/json");
  });
});

describe("environment", () => {
  test("throws if ARTICLES_TABLE env var is not set", async () => {
    delete process.env.ARTICLES_TABLE;
    await expect(
      createHandler(makeMockDdb({}), mockLambda)(makeGatewayEvent("/api/article-summaries", { userId: "user1" })),
    ).rejects.toThrow("ARTICLES_TABLE");
  });
});

describe("POST /api/generate", () => {
  beforeEach(() => {
    process.env.ARTICLES_TABLE = "pulseq-articles";
    process.env.WRITER_FUNCTION_ARN = "arn:aws:lambda:eu-west-1:123456789:function:WriterFunction";
  });
  afterEach(() => { delete process.env.WRITER_FUNCTION_ARN; });

  test("invokes writer Lambda with InvocationType Event and returns 202", async () => {
    const lambda = makeMockLambda();
    const result = await createHandler(makeMockDdb({}), lambda)(
      makeGatewayEvent("/api/generate", undefined, "POST"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(202);
    expect(JSON.parse(result.body as string)).toEqual({ status: "generating" });
    const cmd = (lambda.send as jest.Mock).mock.calls[0][0] as InvokeCommand;
    expect(cmd.input.FunctionName).toBe(process.env.WRITER_FUNCTION_ARN);
    expect(cmd.input.InvocationType).toBe("Event");
  });

  test("returns 500 when Lambda invoke fails", async () => {
    const result = await createHandler(makeMockDdb({}), makeMockLambda(true))(
      makeGatewayEvent("/api/generate", undefined, "POST"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
  });

  test("returns 500 when WRITER_FUNCTION_ARN is missing", async () => {
    delete process.env.WRITER_FUNCTION_ARN;
    const result = await createHandler(makeMockDdb({}), mockLambda)(
      makeGatewayEvent("/api/generate", undefined, "POST"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
    expect(JSON.parse(result.body as string).error).toMatch(/WRITER_FUNCTION_ARN/);
  });

  test("returns 404 for GET /api/generate (wrong method)", async () => {
    const result = await createHandler(makeMockDdb({}), mockLambda)(
      makeGatewayEvent("/api/generate"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(404);
  });
});
