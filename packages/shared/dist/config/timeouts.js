export const TIMEOUTS = {
    singstat: 15000, // WHY: SingStat can be slow for large tables
    mas: 10000, // WHY: MAS is generally responsive
    onemap: 10000, // WHY: OneMap is generally responsive
    ura: 20000, // WHY: URA is the slowest API, especially for transaction data
    datagov: 10000, // WHY: CKAN is generally responsive
};
export const HARD_CAP_TIMEOUT = 30000; // WHY: no API call should ever take more than 30 seconds
//# sourceMappingURL=timeouts.js.map