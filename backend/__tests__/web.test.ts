import { createHandler } from "../index";
import { DynamoDBDocumentClient, QueryCommand } from "@aws-sdk/lib-dynamodb";
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import type { APIGatewayProxyEventV2, APIGatewayProxyStructuredResultV2 } from "aws-lambda";

function makeGatewayEvent(
  rawPath: string,
  queryParams?: Record<string, string>,
  method = "GET",
  body?: string,
): APIGatewayProxyEventV2 {
  return {
    rawPath,
    queryStringParameters: queryParams,
    requestContext: { http: { method } },
    body,
  } as unknown as APIGatewayProxyEventV2;
}

function makeMockS3(shouldFail = false) {
  const send = jest.fn().mockImplementation(() =>
    shouldFail
      ? Promise.reject(new Error("S3 error"))
      : Promise.resolve({}),
  );
  return { send } as unknown as S3Client;
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
const mockS3 = makeMockS3();

describe("GET /api/article-summaries", () => {
  beforeEach(() => { process.env.ARTICLES_TABLE = "pulseq-articles"; });

  test("returns 200 JSON for user1", async () => {
    const result = await createHandler(makeMockDdb(MOCK_DB), mockLambda, mockS3)(
      makeGatewayEvent("/api/article-summaries", { userId: "user1" }),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
    expect(result.headers!["Content-Type"]).toBe("application/json");
    const body = JSON.parse(result.body as string);
    expect(body).toHaveLength(1);
    expect(body[0]).toMatchObject({ id: "abc12", title: "How Load Balancers Work" });
  });

  test("returns only userX's articles, not user1's", async () => {
    const result = await createHandler(makeMockDdb(MOCK_DB), mockLambda, mockS3)(
      makeGatewayEvent("/api/article-summaries", { userId: "userX" }),
    ) as APIGatewayProxyStructuredResultV2;
    const body = JSON.parse(result.body as string);
    expect(body).toHaveLength(1);
    expect(body[0]).toMatchObject({ id: "xyz99", title: "Docker Internals" });
  });

  test("returns 400 when userId is not provided", async () => {
    const result = await createHandler(makeMockDdb(MOCK_DB), mockLambda, mockS3)(
      makeGatewayEvent("/api/article-summaries"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string)).toMatchObject({ error: expect.stringContaining("userId") });
  });

  test("queries with ProjectionExpression that excludes html", async () => {
    const ddb = makeMockDdb(MOCK_DB);
    await createHandler(ddb, mockLambda, mockS3)(makeGatewayEvent("/api/article-summaries", { userId: "user1" }));
    const cmd = (ddb.send as jest.Mock).mock.calls[0][0] as QueryCommand;
    expect(cmd.input.ProjectionExpression).toBeDefined();
    expect(cmd.input.ProjectionExpression).not.toContain("html");
  });

  test("returns empty array for unknown userId", async () => {
    const result = await createHandler(makeMockDdb(MOCK_DB), mockLambda, mockS3)(
      makeGatewayEvent("/api/article-summaries", { userId: "nobody" }),
    ) as APIGatewayProxyStructuredResultV2;
    expect(JSON.parse(result.body as string)).toEqual([]);
  });

  test("propagates DynamoDB errors", async () => {
    await expect(
      createHandler(makeMockDdbThrowing(), mockLambda, mockS3)(makeGatewayEvent("/api/article-summaries", { userId: "user1" })),
    ).rejects.toThrow();
  });
});

describe("GET /api/article/:articleId", () => {
  beforeEach(() => { process.env.ARTICLES_TABLE = "pulseq-articles"; });

  test("returns full article JSON", async () => {
    const result = await createHandler(makeMockDdb(MOCK_DB), mockLambda, mockS3)(
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
    await createHandler(ddb, mockLambda, mockS3)(makeGatewayEvent("/api/article/abc12"));
    const cmd = (ddb.send as jest.Mock).mock.calls[0][0] as QueryCommand;
    expect(cmd.input.IndexName).toBe("ById");
    expect(cmd.input.ExpressionAttributeValues).toMatchObject({ ":id": "abc12" });
  });

  test("returns 404 when article not found", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb(MOCK_DB), mockLambda, mockS3)(
      makeGatewayEvent("/api/article/missing"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(404);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("missing"));
    warnSpy.mockRestore();
  });

  test("propagates DynamoDB errors", async () => {
    await expect(
      createHandler(makeMockDdbThrowing(), mockLambda, mockS3)(makeGatewayEvent("/api/article/abc12")),
    ).rejects.toThrow();
  });
});

describe("unknown paths", () => {
  beforeEach(() => { process.env.ARTICLES_TABLE = "pulseq-articles"; });

  test("returns 404 JSON for unknown routes", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3)(makeGatewayEvent("/unknown")) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(404);
    expect(result.headers!["Content-Type"]).toBe("application/json");
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("/unknown"));
    warnSpy.mockRestore();
  });
});

describe("environment", () => {
  test("throws if ARTICLES_TABLE env var is not set", async () => {
    delete process.env.ARTICLES_TABLE;
    await expect(
      createHandler(makeMockDdb({}), mockLambda, mockS3)(makeGatewayEvent("/api/article-summaries", { userId: "user1" })),
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
    const result = await createHandler(makeMockDdb({}), lambda, mockS3)(
      makeGatewayEvent("/api/generate", undefined, "POST"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(202);
    expect(JSON.parse(result.body as string)).toEqual({ status: "generating" });
    const cmd = (lambda.send as jest.Mock).mock.calls[0][0] as InvokeCommand;
    expect(cmd.input.FunctionName).toBe(process.env.WRITER_FUNCTION_ARN);
    expect(cmd.input.InvocationType).toBe("Event");
  });

  test("returns 500 when Lambda invoke fails", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb({}), makeMockLambda(true), mockS3)(
      makeGatewayEvent("/api/generate", undefined, "POST"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("Lambda invoke failed"), expect.any(Error));
    errorSpy.mockRestore();
  });

  test("returns 500 when WRITER_FUNCTION_ARN is missing", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    delete process.env.WRITER_FUNCTION_ARN;
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3)(
      makeGatewayEvent("/api/generate", undefined, "POST"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
    expect(JSON.parse(result.body as string).error).toMatch(/WRITER_FUNCTION_ARN/);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("WRITER_FUNCTION_ARN"));
    errorSpy.mockRestore();
  });

  test("returns 404 for GET /api/generate (wrong method)", async () => {
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3)(
      makeGatewayEvent("/api/generate"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(404);
  });
});

describe("POST /api/scout", () => {
  beforeEach(() => {
    process.env.ARTICLES_TABLE = "pulseq-articles";
    process.env.SCOUT_FUNCTION_ARN = "arn:aws:lambda:eu-west-1:123456789:function:ScoutFunction";
  });
  afterEach(() => { delete process.env.SCOUT_FUNCTION_ARN; });

  test("invokes scout Lambda with userId payload and returns 202", async () => {
    const lambda = makeMockLambda();
    const result = await createHandler(makeMockDdb({}), lambda, mockS3)(
      makeGatewayEvent("/api/scout", undefined, "POST", JSON.stringify({ userId: "user1" })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(202);
    expect(JSON.parse(result.body as string)).toEqual({ status: "scouting" });
    const cmd = (lambda.send as jest.Mock).mock.calls[0][0] as InvokeCommand;
    expect(cmd.input.FunctionName).toBe(process.env.SCOUT_FUNCTION_ARN);
    expect(cmd.input.InvocationType).toBe("Event");
    const payloadStr = typeof cmd.input.Payload === "string"
      ? cmd.input.Payload
      : Buffer.from(cmd.input.Payload as Uint8Array).toString();
    expect(JSON.parse(payloadStr)).toEqual({ userId: "user1" });
  });

  test("returns 400 when userId is missing", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3)(
      makeGatewayEvent("/api/scout", undefined, "POST", JSON.stringify({})),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/userId/);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("userId"));
    warnSpy.mockRestore();
  });

  test("returns 500 when SCOUT_FUNCTION_ARN is missing", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    delete process.env.SCOUT_FUNCTION_ARN;
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3)(
      makeGatewayEvent("/api/scout", undefined, "POST", JSON.stringify({ userId: "user1" })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
    expect(JSON.parse(result.body as string).error).toMatch(/SCOUT_FUNCTION_ARN/);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("SCOUT_FUNCTION_ARN"));
    errorSpy.mockRestore();
  });

  test("returns 500 when Lambda invoke fails", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb({}), makeMockLambda(true), mockS3)(
      makeGatewayEvent("/api/scout", undefined, "POST", JSON.stringify({ userId: "user1" })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("Lambda invoke failed"), expect.any(Error));
    errorSpy.mockRestore();
  });
});

describe("POST /api/feedback", () => {
  const BUCKET = "pulseq-events";

  function validTimestamp() {
    // Sanitised ISO 8601: colons replaced by hyphens in the time part
    return new Date().toISOString().replace(/:/g, "-");
  }

  function validBody(overrides: Record<string, unknown> = {}) {
    return JSON.stringify({
      articleId: "abc12",
      articleTitle: "How Load Balancers Work",
      userId: "user1",
      reaction: "like",
      clientTimestamp: validTimestamp(),
      ...overrides,
    });
  }

  let warnSpy: jest.SpyInstance;
  beforeEach(() => {
    process.env.ARTICLES_TABLE = "pulseq-articles";
    process.env.EVENTS_BUCKET = BUCKET;
    warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
  });
  afterEach(() => { warnSpy.mockRestore(); });

  test("writes S3 object and returns 200 for valid like", async () => {
    const s3 = makeMockS3();
    const ts = validTimestamp();
    const result = await createHandler(makeMockDdb({}), mockLambda, s3)(
      makeGatewayEvent("/api/feedback", undefined, "POST", JSON.stringify({ articleId: "abc12", articleTitle: "How Load Balancers Work", userId: "user1", reaction: "like", clientTimestamp: ts })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
    const cmd = (s3.send as jest.Mock).mock.calls[0][0] as PutObjectCommand;
    expect(cmd.input.Bucket).toBe(BUCKET);
    expect(cmd.input.Key).toBe(`user1/${ts}_article_abc12_general_feedback.json`);
    expect(cmd.input.ContentType).toBe("application/json");
    expect(JSON.parse(cmd.input.Body as string)).toMatchObject({ articleId: "abc12", articleTitle: "How Load Balancers Work", userId: "user1", reaction: "like", clientTimestamp: ts });
  });

  test("accepts dislike reaction", async () => {
    const s3 = makeMockS3();
    const result = await createHandler(makeMockDdb({}), mockLambda, s3)(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody({ reaction: "dislike" })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
  });

  test("returns 400 for invalid reaction", async () => {
    const result = await createHandler(makeMockDdb({}), mockLambda, makeMockS3())(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody({ reaction: "meh" })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/reaction/);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("meh"));
  });

  test("returns 400 for missing articleId", async () => {
    const result = await createHandler(makeMockDdb({}), mockLambda, makeMockS3())(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody({ articleId: "" })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("articleId"));
  });

  test("returns 400 for timestamp more than 15 minutes old", async () => {
    const old = new Date(Date.now() - 16 * 60 * 1000).toISOString().replace(/:/g, "-");
    const result = await createHandler(makeMockDdb({}), mockLambda, makeMockS3())(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody({ clientTimestamp: old })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/server time/);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("out of range"));
  });

  test("returns 400 for timestamp more than 15 minutes in the future", async () => {
    const future = new Date(Date.now() + 16 * 60 * 1000).toISOString().replace(/:/g, "-");
    const result = await createHandler(makeMockDdb({}), mockLambda, makeMockS3())(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody({ clientTimestamp: future })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("out of range"));
  });

  test("returns 500 when S3 write fails", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb({}), mockLambda, makeMockS3(true))(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody()),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("S3 write failed"), expect.any(Error));
    errorSpy.mockRestore();
  });

  test("returns 500 when EVENTS_BUCKET is not set", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    delete process.env.EVENTS_BUCKET;
    const result = await createHandler(makeMockDdb({}), mockLambda, makeMockS3())(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody()),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
    expect(JSON.parse(result.body as string).error).toMatch(/EVENTS_BUCKET/);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("EVENTS_BUCKET"));
    errorSpy.mockRestore();
  });
});
