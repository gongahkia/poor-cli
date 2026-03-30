import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { artifactStore, ArtifactStore, buildArtifactResult, resetArtifactStoreForTests } from "../artifacts.js";

const tempDirs: string[] = [];

afterEach(() => {
  resetArtifactStoreForTests();
  while (tempDirs.length > 0) {
    const dir = tempDirs.pop();
    if (dir !== undefined) {
      rmSync(dir, { recursive: true, force: true });
    }
  }
  vi.useRealTimers();
});

const createTempDbPath = (): string => {
  const dir = mkdtempSync(join(tmpdir(), "sg-apis-artifacts-"));
  tempDirs.push(dir);
  return join(dir, "artifacts.db");
};

describe("ArtifactStore", () => {
  it("persists artifact records across store restarts", () => {
    const dbPath = createTempDbPath();
    const storeA = new ArtifactStore(dbPath);
    const written = storeA.upsert({
      toolName: "sg_datagov_rows",
      input: { datasetId: "d_demo", limit: 100 },
      kind: "rows",
      title: "Rows artifact",
      payload: { rows: [{ id: 1 }, { id: 2 }] },
      previewText: "Rows preview",
    });
    storeA.close();

    const storeB = new ArtifactStore(dbPath);
    const restored = storeB.read(written.entry.uri);
    storeB.close();

    expect(restored).toMatchObject({
      uri: written.entry.uri,
      toolName: "sg_datagov_rows",
      kind: "rows",
      payload: { rows: [{ id: 1 }, { id: 2 }] },
      previewText: "Rows preview",
    });
  });

  it("drops expired artifacts on read and cleanup", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-03-28T00:00:00.000Z"));

    const dbPath = createTempDbPath();
    const store = new ArtifactStore(dbPath);
    const artifact = store.upsert({
      toolName: "sg_query",
      input: { query: "Transport status now" },
      kind: "realtime-query",
      title: "Realtime query artifact",
      payload: { status: "ok" },
      previewText: "Realtime preview",
      realtime: true,
    });

    vi.setSystemTime(new Date("2026-03-28T00:06:00.000Z"));

    expect(store.read(artifact.entry.uri)).toBeNull();
    expect(store.cleanupExpired()).toBe(0);
    store.close();
  });

  it("keeps the existing artifact result contract while writing to persistent storage", () => {
    resetArtifactStoreForTests(createTempDbPath());

    const result = buildArtifactResult({
      toolName: "sg_singstat_table",
      input: { tableId: "M650151" },
      kind: "table",
      title: "SingStat table artifact",
      fullText: "x".repeat(2_000),
      payload: { tableId: "M650151", rows: [{ year: 2024, value: 1 }] },
      preview: { rows: 1 },
    });

    expect(result.content).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ type: "resource_link" }),
      ]),
    );

    const artifactMeta = (result.structuredContent as Record<string, unknown>)["artifact"] as Record<string, string>;
    const artifactUri = artifactMeta["uri"];
    expect(typeof artifactUri).toBe("string");
    const store = new ArtifactStore(artifactStore.getDbPath());
    const restored = store.read(artifactUri!);
    store.close();

    expect(restored).toMatchObject({
      kind: "table",
      payload: { tableId: "M650151", rows: [{ year: 2024, value: 1 }] },
    });
  });
});
