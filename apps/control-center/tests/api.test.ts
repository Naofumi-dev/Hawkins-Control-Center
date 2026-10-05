import { describe, it, expect, vi, afterEach } from "vitest";
import { checkConfig, signIn, api, OWNER, SUPABASE } from "../src/api";
afterEach(() => vi.unstubAllGlobals());
describe("personal account boundary", () => {
  it("rejects another account and project before login", () => {
    expect(() =>
      checkConfig({
        owner_email: "client@example.com",
        supabase_url: SUPABASE,
        publishable_key: "",
        configured: true,
      }),
    ).toThrow("mismatch");
    expect(() =>
      checkConfig({
        owner_email: OWNER,
        supabase_url: "https://other.supabase.co",
        publishable_key: "",
        configured: true,
      }),
    ).toThrow("mismatch");
  });
  it("never submits credentials while setup is incomplete", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(
      signIn(
        {
          owner_email: OWNER,
          supabase_url: SUPABASE,
          publishable_key: "",
          configured: false,
        },
        "test",
      ),
    ).rejects.toThrow("incomplete");
    expect(fetch).not.toHaveBeenCalled();
  });
  it("rejects a successful OAuth response for the wrong user", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          user: { email: "someone@example.com" },
          access_token: "fake",
        }),
      }),
    );
    await expect(
      signIn(
        {
          owner_email: OWNER,
          supabase_url: SUPABASE,
          publishable_key: "public",
          configured: true,
        },
        "test",
      ),
    ).rejects.toThrow("Wrong account");
  });
  it("reports uncertain action errors instead of claiming success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        json: async () => ({ detail: "Refresh before retry" }),
      }),
    );
    await expect(
      api("test", "/api/drafts/approve", { revision: 1 }),
    ).rejects.toThrow("Refresh before retry");
  });
});
