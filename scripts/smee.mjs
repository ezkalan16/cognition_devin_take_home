import SmeeClient from "smee-client";

const source = process.env.SMEE_URL;
const target = process.env.SMEE_TARGET_URL ?? "http://127.0.0.1:8000/webhook";

if (!source || source.includes("REPLACE_WITH_YOUR_CHANNEL")) {
  throw new Error("Set SMEE_URL in .env to your https://smee.io channel URL");
}

const client = new SmeeClient({ source, target, logger: console });
client.onopen = () => console.info(`Connected to ${source}`);

await client.start();
console.info(`Forwarding webhooks to ${target}`);
