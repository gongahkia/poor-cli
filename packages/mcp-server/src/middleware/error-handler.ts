import { createLogger, ApiError, ValidationError } from "@sg-apis/shared";
import type { ToolResult } from "@sg-apis/shared";

const logger = createLogger("error-handler");

type ToolHandler = (input: unknown) => Promise<ToolResult>;

export const wrapHandler = (handler: ToolHandler): ToolHandler => {
  return async (input: unknown): Promise<ToolResult> => {
    try {
      return await handler(input);
    } catch (error) {
      if (error instanceof ValidationError) {
        return {
          isError: true,
          content: [{ type: "text", text: `Invalid input: ${error.message}` }],
        };
      }
      if (error instanceof ApiError) {
        const retryHint = error.retryable ? " (retryable)" : "";
        return {
          isError: true,
          content: [
            {
              type: "text",
              text: `${error.apiName} error (${error.statusCode}): ${error.message}${retryHint}`,
            },
          ],
        };
      }
      logger.error("unhandled error", {
        error: error instanceof Error ? error.message : String(error),
      });
      return {
        isError: true,
        content: [{ type: "text", text: "Internal error. Check server logs." }],
      };
    }
  };
};
