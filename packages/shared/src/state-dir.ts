import { join } from "node:path";
import { homedir } from "node:os";

const DEFAULT_STATE_DIR = ".sg-apis";

export const resolveStatePath = (fileName: string): string => {
  const root = process.env["SG_APIS_STATE_DIR"] ?? join(homedir(), DEFAULT_STATE_DIR);
  return join(root, fileName);
};
