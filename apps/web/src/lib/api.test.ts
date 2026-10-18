import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, ask, publishDocument, setLicense } from "./api";
import { errorText, refusalText } from "./messages";

function mockFetch(response: Response | Error) {
  const fn = vi.fn(async () => {
    if (response instanceof Error) throw response;
    return response;
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("api", () => {
  it("sends the token and the question and returns the answer", async () => {
    const answer = { question: "q", text: "t [1].", citations: [], refused: false };
    const fetchMock = mockFetch(Response.json(answer));
    expect(await ask("tok", "q")).toEqual(answer);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/v1\/chat$/);
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
    expect(init.body).toBe(JSON.stringify({ question: "q" }));
  });

  it("turns error responses into ApiError with the server's message", async () => {
    mockFetch(Response.json({ detail: "Record the document's license" }, { status: 409 }));
    await expect(publishDocument("tok", "abc")).rejects.toMatchObject({
      status: 409,
      message: "Record the document's license",
    });
  });

  it("sends the license to the document's license endpoint", async () => {
    const fetchMock = mockFetch(Response.json({ id: "abc", license: "CC0" }));
    await setLicense("tok", "abc", "CC0");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/v1\/admin\/documents\/abc\/license$/);
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ license: "CC0" }));
  });

  it("reports an unreachable server", async () => {
    mockFetch(new TypeError("fetch failed"));
    await expect(ask("tok", "q")).rejects.toMatchObject({ status: 0 });
  });
});

describe("messages", () => {
  it("explains each refusal reason and has a fallback", () => {
    expect(refusalText("nothing_relevant_found").title).toMatch(/couldn't find/);
    expect(refusalText("could_not_verify_answer").title).toMatch(/verify/);
    expect(refusalText("something_new").title).toMatch(/can't answer/);
    expect(refusalText(null).title).toMatch(/can't answer/);
  });

  it("turns failures into friendly text", () => {
    expect(errorText(new ApiError(401, "x"))).toMatch(/sign in again/);
    expect(errorText(new ApiError(403, "x"))).toMatch(/role/);
    expect(errorText(new ApiError(429, "x"))).toMatch(/too quickly/);
    expect(errorText(new ApiError(409, "License needed"))).toBe("License needed");
    expect(errorText(new Error("boom"))).toMatch(/went wrong/);
  });
});
