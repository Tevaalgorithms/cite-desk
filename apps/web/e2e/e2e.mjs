// End-to-end checks in a real browser against a real API and web server.
// It starts both itself (throwaway database, offline models) and stops them afterwards.
// Usage (from apps/web):  npm run e2e [screenshot-dir]
//
// To test a stack that is already running (for example the Docker setup behind the proxy),
// give its address and the secret it signs tokens with. Its database must start empty:
//   E2E_BASE_URL=http://localhost:8080 CITEDESK_JWT_DEV_SECRET=<its secret> npm run e2e
import { chromium } from "playwright";
import { execFileSync, spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { randomBytes } from "node:crypto";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const API_PORT = 8123;
const WEB_PORT = 3123;
const external = process.env.E2E_BASE_URL?.replace(/\/$/, "");
const API = external ?? `http://localhost:${API_PORT}`;
const WEB = external ?? `http://localhost:${WEB_PORT}`;
const repoRoot = resolve(import.meta.dirname, "../../..");
const handbook = join(repoRoot, "data/sample/acme-handbook.md");
const shots = process.argv[2] ?? "e2e-screenshots";
mkdirSync(shots, { recursive: true });

const workdir = mkdtempSync(join(tmpdir(), "citedesk-e2e-"));
if (external && !process.env.CITEDESK_JWT_DEV_SECRET) {
  throw new Error("E2E_BASE_URL needs CITEDESK_JWT_DEV_SECRET (the secret the running API signs tokens with)");
}
const env = external
  ? { ...process.env }
  : {
      ...process.env,
      CITEDESK_DATABASE_URL: `sqlite:///${join(workdir, "e2e.db")}`,
      CITEDESK_JWT_DEV_SECRET: randomBytes(32).toString("hex"), // new on every run
      CITEDESK_CORS_ORIGINS: JSON.stringify([WEB]),
      CITEDESK_RATE_LIMIT_PER_MINUTE: "1000",
      CITEDESK_MODELS: "offline",
      // A developer's .env may select Pinecone, OpenAI and tracing. A throwaway test server must
      // never touch those, so it ignores every settings file and states what it uses explicitly.
      CITEDESK_ENV_FILE: "/dev/null",
      CITEDESK_VECTOR_INDEX: "memory",
      CITEDESK_WRITER: "extractive",
      CITEDESK_LANGSMITH_TRACING: "false",
      CITEDESK_ENVIRONMENT: "e2e",
    };
const token = (user, role) =>
  execFileSync("uv", ["run", "citedesk", "token", "--user", user, "--role", role], { cwd: repoRoot, env }).toString().trim();

const children = [];

async function assertPortFree(port, label) {
  const inUse = await fetch(`http://localhost:${port}`).then(() => true, () => false);
  if (inUse) throw new Error(`${label} port ${port} is already in use. Stop whatever is running there and retry.`);
}

function start(command, args, options) {
  // E2E_DEBUG=1 keeps the servers' output so a failing run can be diagnosed.
  const child = spawn(command, args, {
    ...options,
    env: { ...env, ...options.env },
    stdio: process.env.E2E_DEBUG ? ["ignore", "inherit", "inherit"] : "ignore",
    detached: true, // its own process group, so the whole tree (uv, python, node) can be stopped
  });
  children.push(child);
  return child;
}
async function waitFor(url, label) {
  for (let attempt = 0; attempt < 120; attempt++) {
    try {
      if ((await fetch(url)).ok) return;
    } catch { /* not up yet */ }
    await new Promise((resolveWait) => setTimeout(resolveWait, 500));
  }
  throw new Error(`${label} did not start`);
}
function stopAll() {
  for (const child of children) {
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch { /* already stopped */ }
  }
  rmSync(workdir, { recursive: true, force: true });
}
process.on("exit", stopAll);

let page; // set once the browser is open, so failing steps can save a screenshot
const results = [];
async function step(id, name, fn) {
  const started = Date.now();
  try {
    const detail = await fn();
    results.push({ id, name, ok: true, detail: detail ?? "", ms: Date.now() - started });
  } catch (error) {
    await page?.screenshot({ path: `${shots}/FAIL-${id}.png` }).catch(() => {});
    results.push({ id, name, ok: false, detail: String(error.message ?? error).split("\n")[0].slice(0, 220), ms: Date.now() - started });
  }
}
const expect = (cond, msg) => { if (!cond) throw new Error(msg); };

if (!external) {
  await assertPortFree(API_PORT, "API");
  await assertPortFree(WEB_PORT, "Web");
  start("uv", ["run", "citedesk", "serve", "--port", String(API_PORT)], { cwd: repoRoot, env: {} });
  start("npx", ["next", "dev", "--port", String(WEB_PORT)], { cwd: resolve(import.meta.dirname, ".."), env: { NEXT_PUBLIC_API_URL: API } });
}
await waitFor(`${API}/health`, "API");
await waitFor(WEB, "web app");

const tokens = { admin: token("alice", "admin"), analyst: token("bob", "analyst") };
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1200, height: 800 } });
page = await context.newPage();
const consoleErrors = [];
page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
page.on("pageerror", (error) => consoleErrors.push(String(error)));

async function signIn(role, path = "/") {
  await page.goto(`${WEB}${path}`);
  await page.getByLabel("Sign-in token").fill(tokens[role]);
  await page.getByRole("button", { name: "Sign in" }).click();
}
async function signOut() {
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByLabel("Sign-in token").waitFor();
}
async function ask(question) {
  await page.getByLabel("Your question").fill(question);
  await page.getByRole("button", { name: "Ask", exact: true }).click();
}

// ----------------------------------------------------------------------------- sign-in
await step("B1", "sign-in screen rejects a bad token", async () => {
  await page.goto(WEB);
  await page.getByLabel("Sign-in token").fill("not-a-token");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByText("not valid or has expired").waitFor({ timeout: 5000 });
  await page.screenshot({ path: `${shots}/01-sign-in-error.png` });
});
await step("B2", "analyst signs in; no Admin link; example questions shown", async () => {
  await signIn("analyst");
  await page.getByRole("heading", { name: "Ask the handbook" }).waitFor();
  expect((await page.getByRole("link", { name: "Admin" }).count()) === 0, "analyst can see the Admin link");
  expect((await page.locator(".example").count()) >= 3, "no example questions");
  await page.screenshot({ path: `${shots}/02-chat-empty.png` });
});
await step("B2b", "the status bar names the answering model; the built-in writer is Offline with no check button", async () => {
  const badge = page.getByTestId("model-badge");
  await badge.waitFor({ timeout: 8000 });
  const text = (await badge.innerText()).replace(/\s+/g, " ").trim();
  expect(text === "Offline · built-in · extractive quoting", `badge said: ${text}`);
  expect((await page.getByRole("button", { name: "Check connection" }).count()) === 0, "nothing to check for the built-in writer");
  await page.screenshot({ path: `${shots}/02b-model-bar.png` });
});
await step("B3", "before anything is published, a question is refused kindly", async () => {
  await ask("How many vacation days do I get?");
  await page.getByText("couldn't find that in the handbook").waitFor({ timeout: 8000 });
  await page.screenshot({ path: `${shots}/03-refusal.png` });
});
await step("B4", "analyst cannot use the admin console", async () => {
  await page.goto(`${WEB}/admin`);
  await page.getByText("for administrators").waitFor({ timeout: 5000 });
});

// ----------------------------------------------------------------------------- admin
await step("B5", "admin uploads the sample handbook; it appears as a draft", async () => {
  await signOut();
  await signIn("admin", "/admin");
  await page.getByRole("heading", { name: "Documents" }).waitFor();
  await page.getByLabel("File (optional)").setInputFiles(handbook);
  await page.getByLabel("Source", { exact: true }).first().fill("sample data");
  await page.getByRole("button", { name: "Add as draft" }).click();
  await page.getByText("as a draft. Review it").waitFor({ timeout: 8000 });
  await page.locator("tr", { hasText: "acme-handbook" }).getByText("draft").waitFor();
  await page.screenshot({ path: `${shots}/04-admin-draft.png` });
});
await step("B6", "publishing without a license is refused with a clear reason", async () => {
  await page.locator("tr", { hasText: "acme-handbook" }).getByRole("button", { name: "Publish" }).click();
  await page.getByRole("alert").filter({ hasText: "license" }).waitFor({ timeout: 8000 });
  await page.screenshot({ path: `${shots}/05-license-required.png` });
});
await step("B7", "preview shows chunks with their sections", async () => {
  await page.locator("tr", { hasText: "acme-handbook" }).getByRole("button", { name: "Preview" }).click();
  await page.getByText("Time off > Vacation").first().waitFor({ timeout: 5000 });
  await page.getByRole("button", { name: "Close preview" }).click();
});
await step("B8", "adding the same file again is refused and names the existing document", async () => {
  await page.getByLabel("File (optional)").setInputFiles(handbook);
  await page.getByLabel("Source", { exact: true }).first().fill("sample data");
  await page.getByRole("button", { name: "Add as draft" }).click();
  await page.getByRole("alert").filter({ hasText: "already added as \u201cacme-handbook\u201d (draft)" }).waitFor({ timeout: 8000 });
});
await step("B9", "the missing license is added in the table, then publishing works", async () => {
  const row = page.locator("tr", { hasText: "acme-handbook" });
  await row.getByRole("button", { name: "Add license" }).click();
  await row.getByLabel("License for acme-handbook").fill("   ");
  expect(await row.getByRole("button", { name: "Save" }).isDisabled(), "Save should be disabled for a blank license");
  await row.getByLabel("License for acme-handbook").fill("CC0 (synthetic sample)");
  await row.getByRole("button", { name: "Save" }).click();
  await row.getByText("CC0 (synthetic sample)").waitFor({ timeout: 8000 });
  await page.screenshot({ path: `${shots}/06-license-added.png` });
  await row.getByRole("button", { name: "Publish" }).click();
  await row.getByText("published").waitFor({ timeout: 8000 });
  await page.screenshot({ path: `${shots}/06-admin-published.png`, fullPage: true });
});
await step("B10", "audit log records the admin's actions", async () => {
  await page.getByText("alice").first().waitFor({ timeout: 5000 });
  expect((await page.locator(".audit li").count()) >= 3, "audit log too short");
});

// ----------------------------------------------------------------------------- asking
await step("B11", "analyst gets a cited answer; chip opens the passage with the sentence highlighted", async () => {
  await signOut();
  await signIn("analyst");
  await ask("How many vacation days do I get?");
  await page.getByText("20 days of paid vacation").first().waitFor({ timeout: 10000 });
  await page.screenshot({ path: `${shots}/07-answer.png` });
  await page.locator(".chip").first().click();
  const drawer = page.getByRole("dialog", { name: "Source passage" });
  await drawer.waitFor();
  const marked = await drawer.locator("mark").innerText();
  expect(marked.includes("20 days"), `highlight was: ${marked}`);
  expect((await drawer.innerText()).includes("Time off > Vacation"), "section missing in drawer");
  await page.screenshot({ path: `${shots}/08-source-drawer.png` });
  await page.keyboard.press("Escape");
  await drawer.waitFor({ state: "detached" });
});
await step("B12", "a question outside the handbook is refused, not guessed", async () => {
  await ask("What is the capital of France?");
  await page.getByText("couldn't find that in the handbook").last().waitFor({ timeout: 8000 });
});
await step("B13", "keyboard only: type a question and press Enter", async () => {
  await page.getByLabel("Your question").fill("When do I need to return my laptop?");
  await page.keyboard.press("Enter");
  await page.getByText("5 business days").first().waitFor({ timeout: 10000 });
});
await step("B14", "signing out clears the session", async () => {
  await signOut();
  await page.reload();
  await page.getByLabel("Sign-in token").waitFor();
});

// ----------------------------------------------------------------------------- unpublish, layout
await step("B15", "unpublishing removes the content from answers", async () => {
  await signIn("admin", "/admin");
  await page.locator("tr", { hasText: "acme-handbook" }).getByRole("button", { name: "Unpublish" }).click();
  await page.locator("tr", { hasText: "acme-handbook" }).getByText("retired").waitFor({ timeout: 8000 });
  await signOut();
  await signIn("analyst");
  await ask("How many vacation days do I get?");
  await page.getByText("couldn't find that in the handbook").waitFor({ timeout: 8000 });
});
await step("B16", "phone layout has no sideways scrolling", async () => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto(WEB);
  await page.getByRole("heading", { name: "Ask the handbook" }).waitFor();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow <= 0, `page is ${overflow}px wider than the screen`);
  await page.screenshot({ path: `${shots}/09-phone.png` });
});
await step("B17", "no errors in the browser console", async () => {
  const real = consoleErrors.filter((text) => !/Failed to load resource: the server responded with a status of (401|403|409|422)/.test(text));
  if (process.env.E2E_DEBUG) console.log(real.join("\n"));
  expect(real.length === 0, `console errors: ${real.slice(0, 2).join(" | ")}`);
});

await browser.close();
const width = Math.max(...results.map((r) => r.name.length));
for (const r of results) console.log(`${r.ok ? "PASS" : "FAIL"} ${r.id.padEnd(4)} ${r.name.padEnd(width)}  ${r.detail}`);
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} checks passed`);
stopAll();
process.exit(failed ? 1 : 0);
