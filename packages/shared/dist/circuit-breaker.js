import { createLogger } from "./logger.js";
const logger = createLogger("circuit-breaker");
export class CircuitBreaker {
    state = "CLOSED";
    failures = 0;
    lastFailureTime = 0;
    failureThreshold;
    resetTimeout;
    name;
    constructor(name, failureThreshold = 3, // WHY: 3 failures is enough to detect a pattern, not too trigger-happy
    resetTimeout = 60000) {
        this.name = name;
        this.failureThreshold = failureThreshold;
        this.resetTimeout = resetTimeout;
    }
    async execute(fn) {
        if (this.state === "OPEN") {
            if (Date.now() - this.lastFailureTime >= this.resetTimeout) {
                this.state = "HALF_OPEN";
                logger.info("circuit half-open", { name: this.name });
            }
            else {
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
        }
        catch (error) {
            this.failures++;
            this.lastFailureTime = Date.now();
            if (this.failures >= this.failureThreshold) {
                this.state = "OPEN";
                logger.info("circuit opened", { name: this.name, failures: this.failures });
            }
            throw error;
        }
    }
    getState() {
        return this.state;
    }
}
//# sourceMappingURL=circuit-breaker.js.map