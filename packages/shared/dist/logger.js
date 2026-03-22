const LOG_LEVELS = { debug: 0, info: 1, warn: 2, error: 3 };
const getConfiguredLevel = () => {
    const env = process.env["SG_APIS_LOG_LEVEL"];
    if (env !== undefined && env !== "" && env in LOG_LEVELS) {
        return env;
    }
    return "info";
};
export const createLogger = (module) => {
    const minLevel = LOG_LEVELS[getConfiguredLevel()];
    const log = (level, msg, extra) => {
        if (LOG_LEVELS[level] < minLevel)
            return;
        const entry = {
            ts: new Date().toISOString(),
            level,
            module,
            msg,
            ...extra,
        };
        process.stderr.write(JSON.stringify(entry) + "\n");
    };
    return {
        debug: (msg, extra) => log("debug", msg, extra),
        info: (msg, extra) => log("info", msg, extra),
        warn: (msg, extra) => log("warn", msg, extra),
        error: (msg, extra) => log("error", msg, extra),
    };
};
//# sourceMappingURL=logger.js.map