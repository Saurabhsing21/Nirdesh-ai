import assert from "node:assert/strict";
import test from "node:test";

import { resolveApiBaseUrl } from "../src/api/endpoints.ts";

test("production defaults API calls to the page origin", () => {
  assert.equal(resolveApiBaseUrl(undefined, "https://voxloom.xyz"), "https://voxloom.xyz");
  assert.equal(resolveApiBaseUrl("", "https://www.voxloom.xyz"), "https://www.voxloom.xyz");
});

test("an explicit development API URL still overrides the page origin", () => {
  assert.equal(
    resolveApiBaseUrl("http://127.0.0.1:8000/", "http://localhost:5173"),
    "http://127.0.0.1:8000",
  );
});
