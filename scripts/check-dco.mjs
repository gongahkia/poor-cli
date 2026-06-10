import { execFileSync } from "node:child_process";

const signoffPattern = /^Signed-off-by:\s+.+\s+<[^<>\s@]+@[^<>\s]+>$/im;

const getArgValue = (name) => {
  const index = process.argv.indexOf(name);
  if (index === -1) return undefined;
  return process.argv[index + 1];
};

const range = getArgValue("--range");
const message = getArgValue("--message");

const fail = (text) => {
  process.stderr.write(`${text}\n`);
  process.exit(1);
};

if (message !== undefined) {
  if (!signoffPattern.test(message)) {
    fail("DCO check failed: commit message is missing a valid Signed-off-by trailer.");
  }
  process.stdout.write("DCO check OK: provided message has a valid Signed-off-by trailer.\n");
  process.exit(0);
}

const revListArgs = range ? ["rev-list", "--reverse", range] : ["rev-list", "--max-count=1", "HEAD"];
const commits = execFileSync("git", revListArgs, { encoding: "utf8" })
  .split("\n")
  .map((line) => line.trim())
  .filter(Boolean);

if (commits.length === 0) {
  process.stdout.write("DCO check OK: no commits to check.\n");
  process.exit(0);
}

const missing = [];
for (const commit of commits) {
  const subject = execFileSync("git", ["show", "-s", "--format=%s", commit], { encoding: "utf8" }).trim();
  const body = execFileSync("git", ["show", "-s", "--format=%B", commit], { encoding: "utf8" });
  if (!signoffPattern.test(body)) {
    missing.push(`${commit.slice(0, 12)} ${subject}`);
  }
}

if (missing.length > 0) {
  fail(`DCO check failed: missing Signed-off-by trailer on:\n${missing.map((item) => `- ${item}`).join("\n")}`);
}

process.stdout.write(`DCO check OK: ${commits.length} commit(s) have Signed-off-by trailers.\n`);
