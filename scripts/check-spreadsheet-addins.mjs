import { readFile } from "node:fs/promises";

const paths = {
  readme: "examples/spreadsheet-addins/README.md",
  google: "examples/spreadsheet-addins/google-sheets/Code.gs",
  excel: "examples/spreadsheet-addins/excel/functions.js",
};

const entries = Object.fromEntries(
  await Promise.all(Object.entries(paths).map(async ([key, path]) => [key, await readFile(path, "utf8")])),
);

const checks = [
  ["Google Sheets raw function", entries.google.includes("function DUDE_DOSSIER(")],
  ["Google Sheets summary function", entries.google.includes("function DUDE_DOSSIER_SUMMARY(")],
  ["Google Sheets freshness function", entries.google.includes("function DUDE_DOSSIER_FRESHNESS(")],
  ["Google Sheets gateway endpoint", entries.google.includes("/api/v1/sg_business_dossier")],
  ["Google Sheets auth header", entries.google.includes("headers.Authorization")],
  ["Excel raw function", entries.excel.includes("async function DUDE_DOSSIER(")],
  ["Excel custom functions association", entries.excel.includes('CustomFunctions.associate("DUDE.DOSSIER"')],
  ["Excel auth header", entries.excel.includes('headers.set("Authorization"')],
  ["Docs rate limits", entries.readme.includes("Rate Limits") && entries.readme.includes("backoff for 429/5xx")],
  ["Docs auth", entries.readme.includes("short-lived token") && entries.readme.includes("customer-controlled proxy")],
  ["Docs export behavior", entries.readme.includes("Export Behavior") && entries.readme.includes("provenance")],
  ["Docs Excel scope", entries.readme.includes("Office manifest") && entries.readme.includes("AppSource")],
];

const failed = checks.filter(([, passed]) => !passed);
if (failed.length > 0) {
  console.error("Spreadsheet add-in check failed:");
  for (const [label] of failed) {
    console.error(`- ${label}`);
  }
  process.exit(1);
}

console.log(`Spreadsheet add-ins OK: ${checks.length} integration checks passed.`);
