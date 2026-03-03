import { createHandler, buildShell } from "../index";
import { DynamoDBDocumentClient, QueryCommand } from "@aws-sdk/lib-dynamodb";
import type { APIGatewayProxyEventV2, APIGatewayProxyStructuredResultV2 } from "aws-lambda";

// Builds a minimal API Gateway event.
function makeGatewayEvent(id?: string): APIGatewayProxyEventV2 {
  return { pathParameters: id ? { id } : undefined } as unknown as APIGatewayProxyEventV2;
}

function makeMockDdb(items: Record<string, unknown>[]) {
  const send = jest.fn().mockResolvedValue({ Items: items });
  return { send } as unknown as DynamoDBDocumentClient;
}

function makeMockDdbThrowing() {
  const send = jest.fn().mockRejectedValue(new Error("DynamoDB internal error"));
  return { send } as unknown as DynamoDBDocumentClient;
}

const SAMPLE_ITEM = {
  id: "abc12",
  title: "How Load Balancers Work",
  accent: "#0d9488",
  html: '<style>:root { --accent: #0d9488; }</style>\n<div class="header-card"><h1>How Load Balancers Work</h1></div>',
  userid: "user1",
  creation_timestamp: "2026-03-03T14:00:00.000Z",
};

describe("buildShell", () => {
  test("wraps fragment in full HTML with title and stylesheet", () => {
    const html = buildShell("My Title", "<p>body</p>");
    expect(html).toContain("<!DOCTYPE html>");
    expect(html).toContain("<title>My Title</title>");
    expect(html).toContain('<link rel="stylesheet" href="https://d1vjqvihd6azy3.cloudfront.net/style.css">');
    expect(html).toContain("<p>body</p>");
  });
});

describe("GET /{id}", () => {
  beforeEach(() => {
    process.env.ARTICLES_TABLE = "pulseq-articles";
  });

  test("returns assembled HTML for a valid id", async () => {
    const handler = createHandler(makeMockDdb([SAMPLE_ITEM]));
    const result: APIGatewayProxyStructuredResultV2 = await handler(makeGatewayEvent("abc12"));
    expect(result.statusCode).toBe(200);
    expect(result.headers!["Content-Type"]).toBe("text/html; charset=utf-8");
    expect(result.body).toContain("<!DOCTYPE html>");
    expect(result.body).toContain("<title>How Load Balancers Work</title>");
    expect(result.body).toContain(SAMPLE_ITEM.html);
  });

  test("queries the ById GSI with the correct id", async () => {
    const ddb = makeMockDdb([SAMPLE_ITEM]);
    const handler = createHandler(ddb);
    await handler(makeGatewayEvent("abc12"));
    expect(ddb.send).toHaveBeenCalledTimes(1);
    const command = (ddb.send as jest.Mock).mock.calls[0][0] as QueryCommand;
    expect(command.input.IndexName).toBe("ById");
    expect(command.input.ExpressionAttributeValues).toMatchObject({ ":id": "abc12" });
  });

  test("returns 404 when article not found", async () => {
    const handler = createHandler(makeMockDdb([]));
    const result = await handler(makeGatewayEvent("missing"));
    expect(result.statusCode).toBe(404);
  });

  test("returns 404 when no id in path", async () => {
    const ddb = makeMockDdb([]);
    const handler = createHandler(ddb);
    const result = await handler(makeGatewayEvent());
    expect(result.statusCode).toBe(404);
    expect(ddb.send).not.toHaveBeenCalled();
  });

  test("propagates unexpected DynamoDB errors", async () => {
    const handler = createHandler(makeMockDdbThrowing());
    await expect(handler(makeGatewayEvent("abc12"))).rejects.toThrow();
  });

  test("throws if ARTICLES_TABLE env var is not set", async () => {
    delete process.env.ARTICLES_TABLE;
    const handler = createHandler(makeMockDdb([]));
    await expect(handler(makeGatewayEvent("abc12"))).rejects.toThrow("ARTICLES_TABLE environment variable is not set");
  });
});
