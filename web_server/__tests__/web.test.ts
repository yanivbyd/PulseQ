import { createHandler, extractTitle, buildShell } from "../index";
import { GetObjectCommand, NoSuchKey, S3Client } from "@aws-sdk/client-s3";
import type { APIGatewayProxyEventV2, APIGatewayProxyStructuredResultV2 } from "aws-lambda";

interface S3Object {
  bucket: string;
  key: string;
  fileContents: string;
}

// Builds a minimal API Gateway event. The handler only reads pathParameters,
// so the rest of the ~20 required fields are omitted and the type is cast.
function makeGatewayEvent(id?: string): APIGatewayProxyEventV2 {
  return { pathParameters: id ? { id } : undefined } as unknown as APIGatewayProxyEventV2;
}

function makeMockS3(objects: S3Object[]) {
  const send = jest.fn().mockImplementation(async (command: unknown) => {
    if (!(command instanceof GetObjectCommand)) {
      throw new Error(`Unexpected S3 command: ${(command as object).constructor.name}`);
    }
    const match = objects.find(
      (o) => o.bucket === command.input.Bucket && o.key === command.input.Key
    );
    if (!match) {
      throw new NoSuchKey({ message: "The specified key does not exist.", $metadata: {} });
    }
    return { Body: { transformToString: async () => match.fileContents } };
  });
  return { send } as unknown as S3Client;
}

function makeMockS3Throwing(errorName: string) {
  const err = Object.assign(new Error(errorName), { name: errorName });
  const send = jest.fn().mockRejectedValue(err);
  return { send } as unknown as S3Client;
}

const SAMPLE_FRAGMENT = `<style>
  :root { --accent: #0d9488; }
</style>
<div class="header-card">
  <h1>How Load Balancers Work</h1>
  <p class="byline">PulseQ Daily Brief</p>
</div>
<div class="section"><p>Content here.</p></div>`;

describe("extractTitle", () => {
  test("extracts title from h1 tag", () => {
    expect(extractTitle("<h1>My Article</h1>")).toBe("My Article");
  });

  test("falls back to PulseQ when no h1 is present", () => {
    expect(extractTitle("<div>no heading here</div>")).toBe("PulseQ");
  });
});

describe("web handler", () => {
  beforeEach(() => {
    process.env.WEB_BUCKET = "test-bucket";
  });

  test("returns assembled HTML with correct content-type for a valid id", async () => {
    const s3 = makeMockS3([{ bucket: "test-bucket", key: "abc12.html", fileContents: SAMPLE_FRAGMENT }]);
    const handler = createHandler(s3);
    const result: APIGatewayProxyStructuredResultV2 = await handler(makeGatewayEvent("abc12"));
    expect(result.statusCode).toBe(200);
    expect(result.headers!["Content-Type"]).toBe("text/html; charset=utf-8");
    expect(result.body).toContain("<!DOCTYPE html>");
    expect(result.body).toContain('<link rel="stylesheet" href="https://d1vjqvihd6azy3.cloudfront.net/style.css">');
    expect(result.body).toContain("<title>How Load Balancers Work</title>");
    expect(result.body).toContain(SAMPLE_FRAGMENT);
    expect(s3.send).toHaveBeenCalledTimes(1);
  });

  test("returns 404 when object does not exist in S3", async () => {
    const handler = createHandler(makeMockS3([]));
    const result = await handler(makeGatewayEvent("missing"));
    expect(result.statusCode).toBe(404);
  });

  test("returns 404 when no id in path parameters", async () => {
    const s3 = makeMockS3([]);
    const handler = createHandler(s3);
    const result = await handler(makeGatewayEvent());
    expect(result.statusCode).toBe(404);
    expect(s3.send).not.toHaveBeenCalled();
  });

  test("propagates unexpected S3 errors", async () => {
    const handler = createHandler(makeMockS3Throwing("InternalError"));
    await expect(handler(makeGatewayEvent("abc12"))).rejects.toThrow();
  });

  test("throws if WEB_BUCKET env var is not set", async () => {
    delete process.env.WEB_BUCKET;
    const handler = createHandler(makeMockS3([]));
    await expect(handler(makeGatewayEvent("abc12"))).rejects.toThrow("WEB_BUCKET environment variable is not set");
  });
});
