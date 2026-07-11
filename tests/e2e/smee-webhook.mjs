import assert from "node:assert/strict";
import { createHmac, randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { createServer as createTcpServer } from "node:net";
import { spawn } from "node:child_process";
import { access } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import SmeeClient from "smee-client";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const source = process.env.SMEE_URL;
const dependency = `smee-e2e-${randomUUID()}`;
const targetVersion = "9.8.7";
const webhookSecret = "smee-e2e-secret";
const devinApiKey = "cog_smee_e2e";

if (!source || source.includes("REPLACE_WITH_YOUR_CHANNEL")) {
  throw new Error("Set SMEE_URL in .env to your https://smee.io channel URL");
}

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function withTimeout(promise, milliseconds, message) {
  let timeout;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timeout = setTimeout(() => reject(new Error(message)), milliseconds);
      }),
    ]);
  } finally {
    clearTimeout(timeout);
  }
}

async function freePort() {
  const server = createTcpServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const { port } = server.address();
  await new Promise((resolve) => server.close(resolve));
  return port;
}

async function waitForHealth(url, process, logs) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (process.exitCode !== null) {
      throw new Error(`Local app exited early:\n${logs.value}`);
    }
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // The server is still starting.
    }
    await delay(100);
  }
  throw new Error(`Timed out waiting for ${url}\n${logs.value}`);
}

async function stopProcess(process) {
  if (!process || process.exitCode !== null) return;
  process.kill("SIGTERM");
  try {
    await withTimeout(
      new Promise((resolve) => process.once("exit", resolve)),
      3_000,
      "Timed out stopping the local app",
    );
  } catch {
    process.kill("SIGKILL");
  }
}

let resolveCapture;
let rejectCapture;
const capturePromise = new Promise((resolve, reject) => {
  resolveCapture = resolve;
  rejectCapture = reject;
});

const mockDevin = createServer((request, response) => {
  const chunks = [];
  request.on("data", (chunk) => chunks.push(chunk));
  request.on("error", rejectCapture);
  request.on("end", () => {
    try {
      assert.equal(request.method, "POST");
      assert.equal(request.url, "/v1/sessions");
      const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        session_id: "devin-smee-e2e",
        url: "https://app.devin.ai/sessions/smee-e2e",
        is_new_session: true,
      }));
      if (body.prompt?.includes(dependency)) {
        resolveCapture({ headers: request.headers, body });
      }
    } catch (error) {
      response.writeHead(500);
      response.end();
      rejectCapture(error);
    }
  });
});

let app;
let smee;
const appLogs = { value: "" };

try {
  const mockPort = await freePort();
  const appPort = await freePort();
  await new Promise((resolve, reject) => {
    mockDevin.once("error", reject);
    mockDevin.listen(mockPort, "127.0.0.1", resolve);
  });

  const venvPython = path.join(root, ".venv", "bin", "python");
  let python = "python3";
  try {
    await access(venvPython);
    python = venvPython;
  } catch {
    // Fall back to the Python executable on PATH.
  }

  app = spawn(
    python,
    ["-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", String(appPort)],
    {
      cwd: root,
      env: {
        ...process.env,
        DEVIN_API_BASE_URL: `http://127.0.0.1:${mockPort}`,
        DEVIN_API_KEY: devinApiKey,
        TARGET_REPO_URL: "https://github.com/your-org/your-repo",
        GITHUB_WEBHOOK_SECRET: webhookSecret,
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  app.stdout.on("data", (chunk) => { appLogs.value += chunk; });
  app.stderr.on("data", (chunk) => { appLogs.value += chunk; });

  const target = `http://127.0.0.1:${appPort}/webhook`;
  await waitForHealth(`http://127.0.0.1:${appPort}/health`, app, appLogs);

  let connected;
  const connectedPromise = new Promise((resolve) => { connected = resolve; });
  smee = new SmeeClient({ source, target, logger: console });
  smee.onopen = connected;
  await smee.start();
  await withTimeout(connectedPromise, 10_000, `Timed out connecting to ${source}`);

  const payload = {
    action: "opened",
    issue: {
      number: 7,
      title: `Upgrade ${dependency} to ${targetVersion}`,
      body: `Dependency: ${dependency}\nVersion: ${targetVersion}`,
      html_url: "https://github.com/your-org/your-repo/issues/7",
      labels: [{ name: "dependency_upgrade" }],
    },
  };
  const rawBody = JSON.stringify(payload);
  const signature = `sha256=${createHmac("sha256", webhookSecret).update(rawBody).digest("hex")}`;
  const sourceResponse = await fetch(source, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-github-delivery": randomUUID(),
      "x-github-event": "issues",
      "x-hub-signature-256": signature,
    },
    body: rawBody,
  });
  assert.equal(sourceResponse.ok, true, `Smee source returned HTTP ${sourceResponse.status}`);

  const capture = await withTimeout(
    capturePromise,
    30_000,
    `Timed out waiting for the relayed webhook\n${appLogs.value}`,
  );

  assert.equal(capture.headers.authorization, `Bearer ${devinApiKey}`);
  assert.equal(capture.body.title, `Upgrade ${dependency} to ${targetVersion}`);
  assert.equal(capture.body.idempotent, true);
  assert.match(capture.body.prompt, new RegExp(dependency));
  assert.match(capture.body.prompt, new RegExp(targetVersion.replaceAll(".", "\\.")));

  console.info("PASS: Smee relayed the signed GitHub issue webhook to the local app");
  console.info("PASS: The local app created the expected outbound Devin request");
} finally {
  if (smee) await smee.stop();
  await stopProcess(app);
  await new Promise((resolve) => mockDevin.close(resolve));
}
