import { createHandler } from "../index";
import { DynamoDBDocumentClient, DeleteCommand, GetCommand, QueryCommand } from "@aws-sdk/lib-dynamodb";
import { LambdaClient, InvokeCommand } from "@aws-sdk/client-lambda";
import { SFNClient, StartExecutionCommand } from "@aws-sdk/client-sfn";
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

function makeTopicsDdb(topics: Array<{ title: string; description: string }> | null | "error") {
  const send = jest.fn().mockImplementation((cmd: unknown) => {
    if (topics === "error") return Promise.reject(new Error("DDB error"));
    // Topics GetCommand
    const item = topics !== null ? { userId: "user1", topics } : undefined;
    return Promise.resolve({ Item: item });
  });
  return { send } as unknown as DynamoDBDocumentClient;
}

// articles: articleId -> item (for GetCommand)
// inbox: userId -> inbox items array (for QueryCommand)
// DeleteCommand always succeeds unless opts.deleteFails is true.
function makeMockDdb(
  articles: Record<string, Record<string, unknown>>,
  inbox: Record<string, Record<string, unknown>[]> = {},
  opts: { deleteFails?: boolean } = {},
) {
  const send = jest.fn().mockImplementation((cmd: unknown) => {
    if (cmd instanceof DeleteCommand) {
      return opts.deleteFails
        ? Promise.reject(new Error("DynamoDB delete error"))
        : Promise.resolve({});
    }
    if (cmd instanceof GetCommand) {
      const articleId = cmd.input.Key?.articleId as string | undefined;
      if (articleId !== undefined) {
        return Promise.resolve({ Item: articles[articleId] });
      }
      // Topics GetCommand (userId key)
      return Promise.resolve({ Item: undefined });
    }
    if (cmd instanceof QueryCommand) {
      const uid = cmd.input.ExpressionAttributeValues?.[":uid"] as string | undefined;
      if (uid !== undefined) {
        return Promise.resolve({ Items: inbox[uid] ?? [] });
      }
      return Promise.resolve({ Items: [] });
    }
    return Promise.resolve({});
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

function makeMockSfn(shouldFail = false) {
  const send = jest.fn().mockImplementation(() =>
    shouldFail
      ? Promise.reject(new Error("SFN error"))
      : Promise.resolve({ executionArn: "arn:aws:states:eu-west-1:123:execution:SM:id" }),
  );
  return { send } as unknown as SFNClient;
}

const SAMPLE_QUIZ = [{ q: "What is a load balancer?", options: ["A proxy", "A router", "A switch"], answer: 0 }];

const SAMPLE_ARTICLE_ID = "river-cloud-delta-amber-forge-nine";

const SAMPLE_ARTICLE = {
  articleId: SAMPLE_ARTICLE_ID,
  userId: "user1",
  title: "How Load Balancers Work",
  creation_timestamp: "2026-03-03T14:00:00.000Z",
  html: '<div class="header-card"><h1>How Load Balancers Work</h1></div>',
  quiz: JSON.stringify(SAMPLE_QUIZ),
};

const SAMPLE_INBOX_ITEM = {
  userId: "user1",
  articleId: SAMPLE_ARTICLE_ID,
  title: "How Load Balancers Work",
  creation_timestamp: "2026-03-03T14:00:00.000Z",
};

const SAMPLE_INBOX_ITEM_2 = {
  userId: "userX",
  articleId: "oak-frost-veil-surge-lens-coral",
  title: "Docker Internals",
  creation_timestamp: "2026-03-02T10:00:00.000Z",
};

const MOCK_ARTICLES: Record<string, Record<string, unknown>> = {
  [SAMPLE_ARTICLE_ID]: SAMPLE_ARTICLE,
};

const MOCK_INBOX: Record<string, Record<string, unknown>[]> = {
  user1: [SAMPLE_INBOX_ITEM],
  userX: [SAMPLE_INBOX_ITEM_2],
};

const mockLambda = makeMockLambda();
const mockSfn = makeMockSfn();
const mockS3 = makeMockS3();

describe("GET /api/topics", () => {
  const TOPICS = [
    { title: "AI News", description: "Latest AI developments" },
    { title: "Cloud", description: "Cloud computing updates" },
  ];

  beforeEach(() => {
    process.env.ARTICLES_TABLE = "pulseq-articles";
    process.env.USER_INBOX_TABLE = "pulseq-user-inbox";
    process.env.TOPICS_TABLE = "pulseq-topics";
  });
  afterEach(() => { delete process.env.TOPICS_TABLE; });

  test("returns topics for a valid userId", async () => {
    const ddb = makeTopicsDdb(TOPICS);
    const result = await createHandler(ddb, mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/topics", { userId: "user1" }),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
    expect(JSON.parse(result.body as string)).toEqual({ topics: TOPICS });
    const cmd = (ddb.send as jest.Mock).mock.calls[0][0] as GetCommand;
    expect(cmd.input.TableName).toBe("pulseq-topics");
    expect(cmd.input.Key).toEqual({ userId: "user1" });
  });

  test("returns 200 with empty topics when item does not exist in DDB", async () => {
    const result = await createHandler(makeTopicsDdb(null), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/topics", { userId: "user1" }),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
    expect(JSON.parse(result.body as string)).toEqual({ topics: [] });
  });

  test("returns 400 when userId is missing", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    const result = await createHandler(makeTopicsDdb([]), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/topics"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/userId/);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("userId"));
    errorSpy.mockRestore();
  });

  test("returns 500 when TOPICS_TABLE is not set", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    delete process.env.TOPICS_TABLE;
    const result = await createHandler(makeTopicsDdb(TOPICS), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/topics", { userId: "user1" }),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
    expect(JSON.parse(result.body as string).error).toMatch(/TOPICS_TABLE/);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("TOPICS_TABLE"));
    errorSpy.mockRestore();
  });

  test("returns 500 on DDB error", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    const result = await createHandler(makeTopicsDdb("error"), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/topics", { userId: "user1" }),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("DDB read failed"), expect.any(Error));
    errorSpy.mockRestore();
  });
});

describe("GET /api/article-summaries", () => {
  beforeEach(() => {
    process.env.ARTICLES_TABLE = "pulseq-articles";
    process.env.USER_INBOX_TABLE = "pulseq-user-inbox";
  });

  test("returns 200 JSON for user1 from inbox table", async () => {
    const result = await createHandler(makeMockDdb(MOCK_ARTICLES, MOCK_INBOX), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/article-summaries", { userId: "user1" }),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
    const body = JSON.parse(result.body as string);
    expect(body).toHaveLength(1);
    expect(body[0]).toMatchObject({ articleId: SAMPLE_ARTICLE_ID, title: "How Load Balancers Work" });
  });

  test("returns only userX's inbox items", async () => {
    const result = await createHandler(makeMockDdb(MOCK_ARTICLES, MOCK_INBOX), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/article-summaries", { userId: "userX" }),
    ) as APIGatewayProxyStructuredResultV2;
    const body = JSON.parse(result.body as string);
    expect(body).toHaveLength(1);
    expect(body[0]).toMatchObject({ articleId: "oak-frost-veil-surge-lens-coral", title: "Docker Internals" });
  });

  test("returns 400 when userId is not provided", async () => {
    const result = await createHandler(makeMockDdb(MOCK_ARTICLES, MOCK_INBOX), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/article-summaries"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string)).toMatchObject({ error: expect.stringContaining("userId") });
  });

  test("queries USER_INBOX_TABLE with userId key (no filter expression)", async () => {
    const ddb = makeMockDdb(MOCK_ARTICLES, MOCK_INBOX);
    await createHandler(ddb, mockLambda, mockS3, mockSfn)(makeGatewayEvent("/api/article-summaries", { userId: "user1" }));
    const cmd = (ddb.send as jest.Mock).mock.calls[0][0] as QueryCommand;
    expect(cmd.input.TableName).toBe("pulseq-user-inbox");
    expect(cmd.input.KeyConditionExpression).toContain("userId");
    expect(cmd.input.FilterExpression).toBeUndefined();
  });

  test("returns empty array for unknown userId", async () => {
    const result = await createHandler(makeMockDdb(MOCK_ARTICLES, MOCK_INBOX), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/article-summaries", { userId: "nobody" }),
    ) as APIGatewayProxyStructuredResultV2;
    expect(JSON.parse(result.body as string)).toEqual([]);
  });

  test("propagates DynamoDB errors", async () => {
    await expect(
      createHandler(makeMockDdbThrowing(), mockLambda, mockS3, mockSfn)(makeGatewayEvent("/api/article-summaries", { userId: "user1" })),
    ).rejects.toThrow();
  });
});

describe("GET /api/article/:articleId", () => {
  beforeEach(() => {
    process.env.ARTICLES_TABLE = "pulseq-articles";
    process.env.USER_INBOX_TABLE = "pulseq-user-inbox";
  });

  test("returns full article JSON including parsed quiz array via GetItem", async () => {
    const result = await createHandler(makeMockDdb(MOCK_ARTICLES, MOCK_INBOX), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent(`/api/article/${SAMPLE_ARTICLE_ID}`),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
    const body = JSON.parse(result.body as string);
    expect(body.articleId).toBe(SAMPLE_ARTICLE_ID);
    expect(body.title).toBe("How Load Balancers Work");
    expect(body.html).toBe(SAMPLE_ARTICLE.html);
    expect(body.quiz).toEqual(SAMPLE_QUIZ);
    expect(body.userId).toBeUndefined(); // internal field not exposed
  });

  test("returns quiz: [] when DDB quiz field is absent", async () => {
    const articleWithoutQuiz = { ...SAMPLE_ARTICLE } as Record<string, unknown>;
    delete articleWithoutQuiz.quiz;
    const result = await createHandler(makeMockDdb({ [SAMPLE_ARTICLE_ID]: articleWithoutQuiz }, MOCK_INBOX), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent(`/api/article/${SAMPLE_ARTICLE_ID}`),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
    expect(JSON.parse(result.body as string).quiz).toEqual([]);
  });

  test("returns quiz: [] and warns when DDB quiz field contains invalid JSON", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    const articleBadQuiz = { ...SAMPLE_ARTICLE, quiz: "not valid json" };
    const result = await createHandler(makeMockDdb({ [SAMPLE_ARTICLE_ID]: articleBadQuiz }, MOCK_INBOX), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent(`/api/article/${SAMPLE_ARTICLE_ID}`),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
    expect(JSON.parse(result.body as string).quiz).toEqual([]);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("invalid quiz JSON"));
    warnSpy.mockRestore();
  });

  test("uses GetCommand (not QueryCommand) with articleId key", async () => {
    const ddb = makeMockDdb(MOCK_ARTICLES, MOCK_INBOX);
    await createHandler(ddb, mockLambda, mockS3, mockSfn)(makeGatewayEvent(`/api/article/${SAMPLE_ARTICLE_ID}`));
    const cmd = (ddb.send as jest.Mock).mock.calls[0][0];
    expect(cmd).toBeInstanceOf(GetCommand);
    expect((cmd as GetCommand).input.Key).toEqual({ articleId: SAMPLE_ARTICLE_ID });
    expect((cmd as GetCommand).input.TableName).toBe("pulseq-articles");
  });

  test("returns 404 when article not found", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb(MOCK_ARTICLES, MOCK_INBOX), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/article/missing"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(404);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("missing"));
    warnSpy.mockRestore();
  });

  test("propagates DynamoDB errors", async () => {
    await expect(
      createHandler(makeMockDdbThrowing(), mockLambda, mockS3, mockSfn)(makeGatewayEvent(`/api/article/${SAMPLE_ARTICLE_ID}`)),
    ).rejects.toThrow();
  });
});

describe("unknown paths", () => {
  beforeEach(() => {
    process.env.ARTICLES_TABLE = "pulseq-articles";
    process.env.USER_INBOX_TABLE = "pulseq-user-inbox";
  });

  test("returns 404 JSON for unknown routes", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(makeGatewayEvent("/unknown")) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(404);
    expect(result.headers!["Content-Type"]).toBe("application/json");
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("/unknown"));
    warnSpy.mockRestore();
  });
});

describe("environment", () => {
  test("throws if ARTICLES_TABLE env var is not set", async () => {
    delete process.env.ARTICLES_TABLE;
    delete process.env.USER_INBOX_TABLE;
    await expect(
      createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(makeGatewayEvent("/api/article-summaries", { userId: "user1" })),
    ).rejects.toThrow("ARTICLES_TABLE");
  });

  test("throws if USER_INBOX_TABLE env var is not set", async () => {
    process.env.ARTICLES_TABLE = "pulseq-articles";
    delete process.env.USER_INBOX_TABLE;
    await expect(
      createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(makeGatewayEvent("/api/article-summaries", { userId: "user1" })),
    ).rejects.toThrow("USER_INBOX_TABLE");
  });
});

describe("POST /api/generate", () => {
  beforeEach(() => {
    process.env.ARTICLES_TABLE = "pulseq-articles";
    process.env.USER_INBOX_TABLE = "pulseq-user-inbox";
    process.env.WRITER_STATE_MACHINE_ARN = "arn:aws:states:eu-west-1:123456789012:stateMachine:WriterSM";
  });
  afterEach(() => { delete process.env.WRITER_STATE_MACHINE_ARN; });

  test("starts state machine execution with userId payload, returns 202", async () => {
    const sfn = makeMockSfn();
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, sfn)(
      makeGatewayEvent("/api/generate", undefined, "POST", JSON.stringify({ userId: "user1" })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(202);
    expect(JSON.parse(result.body as string)).toEqual({ status: "generating" });
    const cmd = (sfn.send as jest.Mock).mock.calls[0][0] as StartExecutionCommand;
    expect(cmd.input.stateMachineArn).toBe(process.env.WRITER_STATE_MACHINE_ARN);
    expect(JSON.parse(cmd.input.input!)).toEqual({ userId: "user1" });
  });

  test("forwards customTopic in state machine input when provided", async () => {
    const sfn = makeMockSfn();
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, sfn)(
      makeGatewayEvent("/api/generate", undefined, "POST", JSON.stringify({ userId: "user1", customTopic: "quantum computing" })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(202);
    const cmd = (sfn.send as jest.Mock).mock.calls[0][0] as StartExecutionCommand;
    expect(JSON.parse(cmd.input.input!)).toEqual({ userId: "user1", customTopic: "quantum computing" });
  });

  test("omits customTopic from state machine input when not provided", async () => {
    const sfn = makeMockSfn();
    await createHandler(makeMockDdb({}), mockLambda, mockS3, sfn)(
      makeGatewayEvent("/api/generate", undefined, "POST", JSON.stringify({ userId: "user1" })),
    );
    const cmd = (sfn.send as jest.Mock).mock.calls[0][0] as StartExecutionCommand;
    const input = JSON.parse(cmd.input.input!);
    expect(input.customTopic).toBeUndefined();
  });

  test("returns 400 when customTopic exceeds 1000 characters", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    const longTopic = "a".repeat(1001);
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/generate", undefined, "POST", JSON.stringify({ userId: "user1", customTopic: longTopic })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/1000/);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("customTopic"));
    warnSpy.mockRestore();
  });

  test("returns 400 when userId is missing", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/generate", undefined, "POST", JSON.stringify({})),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/userId/);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("userId"));
    warnSpy.mockRestore();
  });

  test("returns 500 when StartExecution fails", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, makeMockSfn(true))(
      makeGatewayEvent("/api/generate", undefined, "POST", JSON.stringify({ userId: "user1" })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("StartExecution failed"), expect.any(Error));
    errorSpy.mockRestore();
  });

  test("returns 500 when WRITER_STATE_MACHINE_ARN is missing", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    delete process.env.WRITER_STATE_MACHINE_ARN;
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/generate", undefined, "POST"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
    expect(JSON.parse(result.body as string).error).toMatch(/WRITER_STATE_MACHINE_ARN/);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("WRITER_STATE_MACHINE_ARN"));
    errorSpy.mockRestore();
  });

  test("returns 404 for GET /api/generate (wrong method)", async () => {
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/generate"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(404);
  });

  test("forwards followUpArticleId and followUpExtraContext in state machine input", async () => {
    const sfn = makeMockSfn();
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, sfn)(
      makeGatewayEvent("/api/generate", undefined, "POST", JSON.stringify({
        userId: "user1",
        followUpArticleId: "orig-abc",
        followUpExtraContext: "focus on costs",
      })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(202);
    const cmd = (sfn.send as jest.Mock).mock.calls[0][0] as StartExecutionCommand;
    expect(JSON.parse(cmd.input.input!)).toEqual({
      userId: "user1",
      followUpArticleId: "orig-abc",
      followUpExtraContext: "focus on costs",
    });
  });

  test("returns 400 when customTopic and followUpArticleId are both provided", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/generate", undefined, "POST", JSON.stringify({
        userId: "user1",
        customTopic: "quantum",
        followUpArticleId: "orig-abc",
        followUpExtraContext: "focus on costs",
      })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/mutually exclusive/);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("mutually exclusive"));
    warnSpy.mockRestore();
  });

  test("returns 400 when followUpArticleId is present but followUpExtraContext is missing", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/generate", undefined, "POST", JSON.stringify({
        userId: "user1",
        followUpArticleId: "orig-abc",
      })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/followUpExtraContext/);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("followUpExtraContext"));
    warnSpy.mockRestore();
  });

  test("returns 400 when followUpExtraContext exceeds 1000 characters", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/generate", undefined, "POST", JSON.stringify({
        userId: "user1",
        followUpArticleId: "orig-abc",
        followUpExtraContext: "x".repeat(1001),
      })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/followUpExtraContext/);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("followUpExtraContext"));
    warnSpy.mockRestore();
  });

  test("returns 400 when followUpArticleId is an empty string", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/generate", undefined, "POST", JSON.stringify({
        userId: "user1",
        followUpArticleId: "",
        followUpExtraContext: "focus on costs",
      })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/followUpArticleId/);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("followUpArticleId"));
    warnSpy.mockRestore();
  });
});

describe("POST /api/scout", () => {
  beforeEach(() => {
    process.env.ARTICLES_TABLE = "pulseq-articles";
    process.env.USER_INBOX_TABLE = "pulseq-user-inbox";
    process.env.SCOUT_FUNCTION_ARN = "arn:aws:lambda:eu-west-1:123456789:function:ScoutFunction";
  });
  afterEach(() => { delete process.env.SCOUT_FUNCTION_ARN; });

  test("invokes scout Lambda with userId payload and returns 202", async () => {
    const lambda = makeMockLambda();
    const result = await createHandler(makeMockDdb({}), lambda, mockS3, mockSfn)(
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
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(
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
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/scout", undefined, "POST", JSON.stringify({ userId: "user1" })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
    expect(JSON.parse(result.body as string).error).toMatch(/SCOUT_FUNCTION_ARN/);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("SCOUT_FUNCTION_ARN"));
    errorSpy.mockRestore();
  });

  test("returns 500 when Lambda invoke fails", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb({}), makeMockLambda(true), mockS3, mockSfn)(
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
    return new Date().toISOString().replace(/:/g, "-");
  }

  function validBody(overrides: Record<string, unknown> = {}) {
    return JSON.stringify({
      articleId: SAMPLE_ARTICLE_ID,
      articleTitle: "How Load Balancers Work",
      userId: "user1",
      content: { type: "reaction", reaction: "like" },
      clientTimestamp: validTimestamp(),
      ...overrides,
    });
  }

  let warnSpy: jest.SpyInstance;
  beforeEach(() => {
    process.env.ARTICLES_TABLE = "pulseq-articles";
    process.env.USER_INBOX_TABLE = "pulseq-user-inbox";
    process.env.EVENTS_BUCKET = BUCKET;
    warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
  });
  afterEach(() => { warnSpy.mockRestore(); });

  test("reaction event: writes correct S3 key and envelope, returns 200", async () => {
    const s3 = makeMockS3();
    const ts = validTimestamp();
    const result = await createHandler(makeMockDdb({}), mockLambda, s3, mockSfn)(
      makeGatewayEvent("/api/feedback", undefined, "POST", JSON.stringify({
        articleId: SAMPLE_ARTICLE_ID, articleTitle: "How Load Balancers Work", userId: "user1",
        content: { type: "reaction", reaction: "like" }, clientTimestamp: ts,
      })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
    const cmd = (s3.send as jest.Mock).mock.calls[0][0] as PutObjectCommand;
    expect(cmd.input.Bucket).toBe(BUCKET);
    expect(cmd.input.Key).toBe(`user1/${ts}_article_${SAMPLE_ARTICLE_ID}_feedback.json`);
    expect(cmd.input.ContentType).toBe("application/json");
    const written = JSON.parse(cmd.input.Body as string);
    expect(written).toMatchObject({ articleId: SAMPLE_ARTICLE_ID, articleTitle: "How Load Balancers Work", userId: "user1", clientTimestamp: ts });
    expect(written.content).toEqual({ type: "reaction", reaction: "like" });
  });

  test("freeText event: writes correct S3 envelope, returns 200", async () => {
    const s3 = makeMockS3();
    const ts = validTimestamp();
    const result = await createHandler(makeMockDdb({}), mockLambda, s3, mockSfn)(
      makeGatewayEvent("/api/feedback", undefined, "POST", JSON.stringify({
        articleId: SAMPLE_ARTICLE_ID, articleTitle: "How Load Balancers Work", userId: "user1",
        content: { type: "freeText", text: "Great explanation of CRDTs" }, clientTimestamp: ts,
      })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
    const cmd = (s3.send as jest.Mock).mock.calls[0][0] as PutObjectCommand;
    const written = JSON.parse(cmd.input.Body as string);
    expect(written.content).toEqual({ type: "freeText", text: "Great explanation of CRDTs" });
  });

  test("accepts dislike reaction", async () => {
    const s3 = makeMockS3();
    const result = await createHandler(makeMockDdb({}), mockLambda, s3, mockSfn)(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody({ content: { type: "reaction", reaction: "dislike" } })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
  });

  test("returns 400 for missing/null content", async () => {
    const result = await createHandler(makeMockDdb({}), mockLambda, makeMockS3(), mockSfn)(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody({ content: null })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/content/);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("content"));
  });

  test("returns 400 for unknown content.type", async () => {
    const result = await createHandler(makeMockDdb({}), mockLambda, makeMockS3(), mockSfn)(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody({ content: { type: "unknown" } })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/content\.type/);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("content.type"));
  });

  test("returns 400 for invalid reaction value", async () => {
    const result = await createHandler(makeMockDdb({}), mockLambda, makeMockS3(), mockSfn)(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody({ content: { type: "reaction", reaction: "meh" } })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/content\.reaction/);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("content.reaction"));
  });

  test("returns 400 when content.text exceeds 5000 characters", async () => {
    const longText = "a".repeat(5001);
    const result = await createHandler(makeMockDdb({}), mockLambda, makeMockS3(), mockSfn)(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody({ content: { type: "freeText", text: longText } })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/5000/);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("content.text"));
  });

  test("returns 400 for missing articleId", async () => {
    const result = await createHandler(makeMockDdb({}), mockLambda, makeMockS3(), mockSfn)(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody({ articleId: "" })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("articleId"));
  });

  test("returns 400 for timestamp more than 15 minutes old", async () => {
    const old = new Date(Date.now() - 16 * 60 * 1000).toISOString().replace(/:/g, "-");
    const result = await createHandler(makeMockDdb({}), mockLambda, makeMockS3(), mockSfn)(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody({ clientTimestamp: old })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/server time/);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("out of range"));
  });

  test("returns 400 for timestamp more than 15 minutes in the future", async () => {
    const future = new Date(Date.now() + 16 * 60 * 1000).toISOString().replace(/:/g, "-");
    const result = await createHandler(makeMockDdb({}), mockLambda, makeMockS3(), mockSfn)(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody({ clientTimestamp: future })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("out of range"));
  });

  test("returns 500 when S3 write fails", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    const result = await createHandler(makeMockDdb({}), mockLambda, makeMockS3(true), mockSfn)(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody()),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("S3 write failed"), expect.any(Error));
    errorSpy.mockRestore();
  });

  test("returns 500 when EVENTS_BUCKET is not set", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    delete process.env.EVENTS_BUCKET;
    const result = await createHandler(makeMockDdb({}), mockLambda, makeMockS3(), mockSfn)(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody()),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
    expect(JSON.parse(result.body as string).error).toMatch(/EVENTS_BUCKET/);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("EVENTS_BUCKET"));
    errorSpy.mockRestore();
  });

  test("removes article from inbox (DeleteItem) for both reaction and freeText events", async () => {
    const infoSpy = jest.spyOn(console, "info").mockImplementation(() => {});
    for (const content of [{ type: "reaction", reaction: "like" }, { type: "freeText", text: "nice" }]) {
      const ddb = makeMockDdb(MOCK_ARTICLES, MOCK_INBOX);
      const result = await createHandler(ddb, mockLambda, makeMockS3(), mockSfn)(
        makeGatewayEvent("/api/feedback", undefined, "POST", validBody({ content })),
      ) as APIGatewayProxyStructuredResultV2;
      expect(result.statusCode).toBe(200);
      const calls = (ddb.send as jest.Mock).mock.calls.map((c: unknown[]) => c[0]);
      const deleteCall = calls.find((c: unknown) => c instanceof DeleteCommand) as DeleteCommand | undefined;
      expect(deleteCall).toBeDefined();
      expect(deleteCall!.input.Key).toEqual({ userId: "user1", articleId: SAMPLE_ARTICLE_ID });
      expect(deleteCall!.input.TableName).toBe("pulseq-user-inbox");
    }
    expect(infoSpy).toHaveBeenCalled();
    infoSpy.mockRestore();
  });

  test("returns 200 and warns when inbox DeleteItem fails (fail-open)", async () => {
    const warnSpy2 = jest.spyOn(console, "warn").mockImplementation(() => {});
    const ddb = makeMockDdb(MOCK_ARTICLES, MOCK_INBOX, { deleteFails: true });
    const result = await createHandler(ddb, mockLambda, makeMockS3(), mockSfn)(
      makeGatewayEvent("/api/feedback", undefined, "POST", validBody()),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
    expect(warnSpy2).toHaveBeenCalledWith(expect.stringContaining("failed to remove article"), expect.any(Error));
    warnSpy2.mockRestore();
  });
});

describe("POST /api/mark-read", () => {
  function validMarkReadBody(overrides: Record<string, unknown> = {}) {
    return JSON.stringify({
      userId: "user1",
      articleId: SAMPLE_ARTICLE_ID,
      ...overrides,
    });
  }

  let errorSpy: jest.SpyInstance;
  beforeEach(() => {
    process.env.ARTICLES_TABLE = "pulseq-articles";
    process.env.USER_INBOX_TABLE = "pulseq-user-inbox";
    errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => { errorSpy.mockRestore(); });

  test("deletes item from user inbox and returns 200", async () => {
    const logSpy = jest.spyOn(console, "log").mockImplementation(() => {});
    const ddb = makeMockDdb(MOCK_ARTICLES, MOCK_INBOX);
    const result = await createHandler(ddb, mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/mark-read", undefined, "POST", validMarkReadBody()),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(200);
    expect(JSON.parse(result.body as string)).toEqual({});
    const calls = (ddb.send as jest.Mock).mock.calls.map((c: unknown[]) => c[0]);
    const deleteCall = calls.find((c: unknown) => c instanceof DeleteCommand) as DeleteCommand;
    expect(deleteCall).toBeDefined();
    expect(deleteCall.input.TableName).toBe("pulseq-user-inbox");
    expect(deleteCall.input.Key).toEqual({ userId: "user1", articleId: SAMPLE_ARTICLE_ID });
    expect(logSpy).toHaveBeenCalled();
    logSpy.mockRestore();
  });

  test("returns 400 for invalid JSON body", async () => {
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/mark-read", undefined, "POST", "not-json"),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("not-json"));
  });

  test("returns 400 for missing userId", async () => {
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/mark-read", undefined, "POST", validMarkReadBody({ userId: "" })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(JSON.parse(result.body as string).error).toMatch(/userId/);
    expect(errorSpy).toHaveBeenCalled();
  });

  test("returns 400 for missing articleId", async () => {
    const result = await createHandler(makeMockDdb({}), mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/mark-read", undefined, "POST", validMarkReadBody({ articleId: "" })),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(400);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("articleId"));
  });

  test("returns 500 when DeleteItem fails", async () => {
    const ddb = makeMockDdb(MOCK_ARTICLES, MOCK_INBOX, { deleteFails: true });
    const result = await createHandler(ddb, mockLambda, mockS3, mockSfn)(
      makeGatewayEvent("/api/mark-read", undefined, "POST", validMarkReadBody()),
    ) as APIGatewayProxyStructuredResultV2;
    expect(result.statusCode).toBe(500);
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("DeleteItem failed"), expect.any(Error));
  });
});
