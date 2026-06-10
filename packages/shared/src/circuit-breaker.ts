import { createLogger } from "./logger.js";

const logger = createLogger("circuit-breaker");

type CircuitState = "CLOSED" | "OPEN" | "HALF_OPEN";

export class CircuitBreaker {
  private state: CircuitState = "CLOSED";
  private failures = 0;
  private lastFailureTime = 0;
  private readonly failureThreshold: number;
  private readonly resetTimeout: number;
  private readonly name: string;

  constructor(
    name: string,
    failureThreshold = 3, // WHY: 3 failures is enough to detect a pattern, not too trigger-happy
    resetTimeout = 60000, // WHY: 60 seconds gives the API time to recover
  ) {
    this.name = name;
    this.failureThreshold = failureThreshold;
    this.resetTimeout = resetTimeout;
  }

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state === "OPEN") {
      if (Date.now() - this.lastFailureTime >= this.resetTimeout) {
        this.state = "HALF_OPEN";
        logger.info("circuit half-open", { name: this.name });
      } else {
        throw new Error(`Circuit breaker OPEN for ${this.name}. Try again later.`);
      }
    }

    try {
      const result = await fn();
      if (this.state === "HALF_OPEN") {
        this.state = "CLOSED";
        this.failures = 0;
        logger.info("circuit closed", { name: this.name });
      }
      return result;
    } catch (error) {
      this.failures++;
      this.lastFailureTime = Date.now();
      if (this.failures >= this.failureThreshold) {
        this.state = "OPEN";
        logger.info("circuit opened", { name: this.name, failures: this.failures });
      }
      throw error;
    }
  }

  getState(): CircuitState {
    return this.state;
  }
}
