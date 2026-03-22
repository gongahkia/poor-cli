type CircuitState = "CLOSED" | "OPEN" | "HALF_OPEN";
export declare class CircuitBreaker {
    private state;
    private failures;
    private lastFailureTime;
    private readonly failureThreshold;
    private readonly resetTimeout;
    private readonly name;
    constructor(name: string, failureThreshold?: number, // WHY: 3 failures is enough to detect a pattern, not too trigger-happy
    resetTimeout?: number);
    execute<T>(fn: () => Promise<T>): Promise<T>;
    getState(): CircuitState;
}
export {};
//# sourceMappingURL=circuit-breaker.d.ts.map