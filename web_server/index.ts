import { S3Client, GetObjectCommand, NoSuchKey } from "@aws-sdk/client-s3";
import type { APIGatewayProxyEventV2, APIGatewayProxyStructuredResultV2 } from "aws-lambda";

const CSS_URL = "https://d1vjqvihd6azy3.cloudfront.net/style.css";

export function extractTitle(fragment: string): string {
  const match = fragment.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i);
  return match ? match[1] : "PulseQ";
}

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

export function createHandler(s3Client: S3Client) {
  return async function (event: APIGatewayProxyEventV2): Promise<APIGatewayProxyStructuredResultV2> {
    const bucket = process.env.WEB_BUCKET;
    if (!bucket) throw new Error("WEB_BUCKET environment variable is not set");
    const id = event.pathParameters?.id;
    if (!id) {
      return { statusCode: 404, body: "Not Found" };
    }
    try {
      const response = await s3Client.send(
        new GetObjectCommand({ Bucket: bucket, Key: `${id}.html` })
      );
      const fragment = await response.Body!.transformToString("utf-8");
      const title = extractTitle(fragment);
      return {
        statusCode: 200,
        headers: { "Content-Type": "text/html; charset=utf-8" },
        body: buildShell(title, fragment),
      };
    } catch (err: unknown) {
      if (err instanceof NoSuchKey) {
        return { statusCode: 404, body: "Not Found" };
      }
      throw err;
    }
  };
}

const s3 = new S3Client({ region: "eu-west-1" });
export const handler = createHandler(s3);
