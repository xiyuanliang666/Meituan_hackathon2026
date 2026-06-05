#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

const DEFAULT_PUBLIC_BASE_URL = process.env.PUBLIC_BASE_URL || "http://127.0.0.1:8000/static";

function parseArgs(argv) {
  const args = {
    url: "",
    postId: "",
    userDataDir: path.resolve("backend/.playwright-xhs-profile"),
    outputPath: "",
    headless: true,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--url") args.url = argv[++i] || "";
    else if (arg === "--post-id") args.postId = argv[++i] || "";
    else if (arg === "--user-data-dir") args.userDataDir = path.resolve(argv[++i] || "");
    else if (arg === "--output-path") args.outputPath = argv[++i] || "";
    else if (arg === "--headed") args.headless = false;
  }

  if (!args.url || !args.postId || !args.outputPath) {
    throw new Error("Usage: node capture_xhs_post_cover.mjs --url <source_url> --post-id <post_id> --output-path <abs_output_path> [--user-data-dir <dir>]");
  }
  return args;
}

function publicUrlFromOutput(outputPath) {
  const marker = `${path.sep}storage${path.sep}`;
  const normalized = path.resolve(outputPath);
  const index = normalized.lastIndexOf(marker);
  if (index < 0) return "";
  const rel = normalized.slice(index + marker.length).split(path.sep).join("/");
  return `${DEFAULT_PUBLIC_BASE_URL.replace(/\/$/, "")}/${rel}`;
}

async function waitForNoteSurface(page) {
  const selectors = ["#detail-title", "#detail-desc", ".note-content", ".comments-el", ".engage-bar"];
  for (let attempt = 0; attempt < 8; attempt += 1) {
    for (const selector of selectors) {
      try {
        await page.waitForSelector(selector, { timeout: 1200 });
        return true;
      } catch {}
    }
    await page.waitForTimeout(600);
  }
  return false;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const { chromium } = await import("playwright");
  fs.mkdirSync(args.userDataDir, { recursive: true });
  fs.mkdirSync(path.dirname(args.outputPath), { recursive: true });

  const context = await chromium.launchPersistentContext(args.userDataDir, {
    headless: args.headless,
    viewport: { width: 1440, height: 980 },
    args: ["--disable-crashpad", "--disable-crash-reporter", "--disable-breakpad"],
  });

  try {
    const page = context.pages()[0] || (await context.newPage());
    await page.goto(args.url, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(2000);
    await waitForNoteSurface(page);
    const bytes = await page.screenshot({ fullPage: false, type: "jpeg", quality: 84 });
    fs.writeFileSync(args.outputPath, bytes);
    const url = publicUrlFromOutput(args.outputPath);
    process.stdout.write(JSON.stringify({ post_id: args.postId, image_url: url, output_path: args.outputPath }));
  } finally {
    await context.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
