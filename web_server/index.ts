import { S3Client, GetObjectCommand, NoSuchKey } from "@aws-sdk/client-s3";
import type { APIGatewayProxyEventV2, APIGatewayProxyStructuredResultV2 } from "aws-lambda";

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
      const html = await response.Body!.transformToString("utf-8");
      return {
        statusCode: 200,
        headers: { "Content-Type": "text/html; charset=utf-8" },
        body: html,
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
