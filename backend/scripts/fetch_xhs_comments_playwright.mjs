#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import { createHash } from "node:crypto";

const DEFAULT_COMMENT_LIMIT = 120;
const DEFAULT_LOGIN_WAIT_SECONDS = 60;
const DEFAULT_PUBLIC_BASE_URL = process.env.PUBLIC_BASE_URL || "http://127.0.0.1:8000/static";
const COMMENT_CANDIDATE_SELECTOR =
  ".comment-item, [class*='commentItem'], .parent-comment, .sub-comment-item, [class*='subComment'], [class*='reply-item'], .comments-container > div, [class*='comment-list'] > div";

function parseArgs(argv) {
  const args = {
    input: "",
    output: "",
    rawCommentsFile: "",
    userDataDir: path.resolve(".playwright-xhs-profile"),
    headless: false,
    limit: null,
    postId: "",
    commentLimit: DEFAULT_COMMENT_LIMIT,
    loginWaitSeconds: DEFAULT_LOGIN_WAIT_SECONDS,
    resume: false,
    fromStart: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--input") args.input = argv[++i] || "";
    else if (arg === "--output") args.output = argv[++i] || "";
    else if (arg === "--raw-comments-file") args.rawCommentsFile = argv[++i] || "";
    else if (arg === "--user-data-dir") args.userDataDir = path.resolve(argv[++i] || "");
    else if (arg === "--limit") args.limit = Number.parseInt(argv[++i] || "", 10);
    else if (arg === "--post-id") args.postId = argv[++i] || "";
    else if (arg === "--comment-limit") args.commentLimit = Number.parseInt(argv[++i] || "", 10);
    else if (arg === "--login-wait-seconds") args.loginWaitSeconds = Number.parseInt(argv[++i] || "", 10);
    else if (arg === "--resume") args.resume = true;
    else if (arg === "--from-start") args.fromStart = true;
    else if (arg === "--headless") args.headless = true;
  }

  if (!args.rawCommentsFile) {
    const outputPath = path.resolve(args.output);
    const parsed = path.parse(outputPath);
    args.rawCommentsFile = path.join(parsed.dir, `${parsed.name}_raw_comments.json`);
  } else {
    args.rawCommentsFile = path.resolve(args.rawCommentsFile);
  }

  if (args.resume && args.fromStart) {
    throw new Error("Cannot use --resume and --from-start at the same time.");
  }

  if (!args.input || !args.output) {
    throw new Error(
      "Usage: node backend/scripts/fetch_xhs_comments_playwright.mjs --input <json> --output <json> [--user-data-dir <dir>] [--limit N] [--comment-limit N] [--login-wait-seconds N] [--headless]",
    );
  }
  return args;
}

function ensureCommentDefaults(post) {
  if (typeof post.comment_sample_count !== "number") post.comment_sample_count = 0;
  if (typeof post.comment_fetch_status !== "string") post.comment_fetch_status = "pending";
  if (!post.comment_insights || typeof post.comment_insights !== "object") {
    post.comment_insights = {
      status: "pending",
      comment_summary: "",
      summary: "",
      estimated_total_comment_count: 0,
      fetched_comment_count: 0,
      comment_coverage_rate: 0,
      sampling_strategy: [],
      confidence_penalty: 0,
      style_tags: [],
      user_demands: [],
      pain_points: [],
      social_proofs: [],
      purchase_intents: [],
      negative_feedbacks: [],
      risk_flags: [],
      not_suitable_for: [],
      failure_cases: [],
      sentiment: "unknown",
      positive_signals: [],
    };
  }
}

function normalizeCommentLimit(value) {
  if (!Number.isFinite(value) || value <= 0) return Number.MAX_SAFE_INTEGER;
  return value;
}

function loadRawCommentStore(rawCommentsFile) {
  try {
    const payload = JSON.parse(fs.readFileSync(rawCommentsFile, "utf-8"));
    if (payload && typeof payload === "object" && payload.posts && typeof payload.posts === "object") {
      return payload;
    }
  } catch {}
  return { posts: {} };
}

function writeRawCommentStore(rawCommentsFile, store) {
  fs.writeFileSync(rawCommentsFile, JSON.stringify(store, null, 2), "utf-8");
}

function storageRootFromOutput(outputPath) {
  return path.resolve(path.dirname(outputPath), "..", "storage");
}

function publicStaticUrl(relPath) {
  return `${DEFAULT_PUBLIC_BASE_URL.replace(/\/$/, "")}/${String(relPath || "").replace(/^\//, "")}`;
}

async function capturePostFallbackScreenshot(page, outputPath, postId) {
  const safePostId = String(postId || "").trim();
  if (!safePostId) return "";
  try {
    const bytes = await page.screenshot({ fullPage: false, type: "jpeg", quality: 82 });
    const digest = createHash("sha1").update(safePostId).digest("hex").slice(0, 12);
    const relPath = path.join("trend_post_captures", `${safePostId}-${digest}.jpg`);
    const absPath = path.join(storageRootFromOutput(outputPath), relPath);
    fs.mkdirSync(path.dirname(absPath), { recursive: true });
    fs.writeFileSync(absPath, bytes);
    return publicStaticUrl(relPath);
  } catch {
    return "";
  }
}

function hasFetchedComments(post) {
  return post.comment_fetch_status === "done" || post.comment_fetch_status === "unavailable";
}

function normalizeCommentContent(content) {
  return String(content || "")
    .replace(/\s+/g, " ")
    .replace(/展开\s*\d+\s*条回复/g, " ")
    .replace(/(?:展开更多回复|查看全部回复|更多回复|展开回复)/g, " ")
    .replace(/(?:赞|回复)\s*$/g, " ")
    .replace(/(?:作者)\s*/g, " ")
    .replace(/\b(?:今天|昨天|前天|\d{2}-\d{2}|\d{4}-\d{2}-\d{2}|\d+\s*小时前|\d+\s*天前)\b/g, " ")
    .replace(/\b(?:北京|上海|广东|浙江|江苏|福建|山东|河南|河北|四川|重庆|天津|湖北|湖南|陕西|山西|安徽|江西|广西|云南|贵州|海南|吉林|辽宁|黑龙江|甘肃|青海|宁夏|新疆|西藏|内蒙古|香港|澳门|台湾)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function parseCountValue(value) {
  const text = String(value || "").trim().toLowerCase();
  if (!text) return 0;
  const match = text.match(/(\d+(?:\.\d+)?)/);
  if (!match) return 0;
  let number = Number.parseFloat(match[1]);
  if (!Number.isFinite(number)) return 0;
  if (text.includes("万") || text.endsWith("w")) number *= 10000;
  if (text.includes("千") || text.endsWith("k")) number *= 1000;
  return Math.trunc(number);
}

function buildTimeScore(commentTimeText) {
  const text = String(commentTimeText || "").trim();
  if (!text) return 0;
  if (/刚刚/.test(text)) return 100;
  if (/分钟/.test(text)) return 95;
  if (/小时/.test(text)) return 90;
  if (/今天/.test(text)) return 85;
  if (/昨天/.test(text)) return 80;
  if (/前天/.test(text)) return 75;
  if (/\d{4}-\d{2}-\d{2}/.test(text)) return 55;
  if (/\d{2}-\d{2}/.test(text)) return 50;
  if (/\d+\s*天前/.test(text)) return 60;
  return 40;
}

function splitTimeAndLocation(rawText) {
  const text = String(rawText || "").trim();
  if (!text) return { comment_time_text: "", comment_location_text: "" };
  const patterns = [
    /^(刚刚|今天|昨天|前天)(.*)$/,
    /^(\d+\s*分钟前)(.*)$/,
    /^(\d+\s*小时前)(.*)$/,
    /^(\d+\s*天前)(.*)$/,
    /^(\d{4}-\d{2}-\d{2})(.*)$/,
    /^(\d{2}-\d{2})(.*)$/,
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match) {
      return {
        comment_time_text: String(match[1] || "").trim(),
        comment_location_text: String(match[2] || "").trim(),
      };
    }
  }
  return { comment_time_text: text, comment_location_text: "" };
}

function computePriorityComponents(item) {
  const likeScore = Math.min(40, Math.log10((Number(item.like_count) || 0) + 1) * 12);
  const recencyScore = buildTimeScore(item.comment_time_text) * 0.35;
  const replyScore = item.has_replies ? 15 + Math.min(10, Number(item.reply_count_estimate || 0)) : 0;
  return {
    like_score: Number(likeScore.toFixed(2)),
    recency_score: Number(recencyScore.toFixed(2)),
    reply_score: Number(replyScore.toFixed(2)),
  };
}

function computePriorityScore(item) {
  const components = computePriorityComponents(item);
  return Number((components.like_score + components.recency_score + components.reply_score).toFixed(2));
}

function prioritizeComments(comments, limit) {
  const enriched = comments.map((item) => ({
    ...item,
    priority_components: item.priority_components || computePriorityComponents(item),
    priority_score: Number.isFinite(item.priority_score) ? item.priority_score : computePriorityScore(item),
    sampling_bucket: "fallback",
  }));
  const latestQuota = Math.max(1, Math.round(Math.min(limit, enriched.length) * 0.25));
  const latestIds = new Set(
    [...enriched]
      .sort((a, b) => buildTimeScore(b.comment_time_text) - buildTimeScore(a.comment_time_text) || b.priority_score - a.priority_score)
      .slice(0, latestQuota)
      .map((item) => `${item.author_name}\n${item.content}`),
  );
  for (const item of enriched) {
    if ((Number(item.like_count) || 0) >= 20) item.sampling_bucket = "top_liked";
    else if (latestIds.has(`${item.author_name}\n${item.content}`)) item.sampling_bucket = "latest";
    else if (item.has_replies || (Number(item.reply_count_estimate) || 0) > 0) item.sampling_bucket = "threaded";
    else item.sampling_bucket = "fallback";
  }

  if (!Number.isFinite(limit) || limit >= enriched.length) {
    return {
      comments: enriched,
      stats: {
        selectedTopLiked: enriched.filter((item) => item.sampling_bucket === "top_liked").length,
        selectedLatest: enriched.filter((item) => item.sampling_bucket === "latest").length,
        selectedThreaded: enriched.filter((item) => item.sampling_bucket === "threaded").length,
        selectedFallback: enriched.filter((item) => item.sampling_bucket === "fallback").length,
      },
    };
  }

  const buckets = {
    top_liked: [],
    latest: [],
    threaded: [],
    fallback: [],
  };
  for (const item of enriched) {
    buckets[item.sampling_bucket].push(item);
  }
  buckets.top_liked.sort((a, b) => (b.like_count || 0) - (a.like_count || 0) || b.priority_score - a.priority_score);
  buckets.latest.sort((a, b) => buildTimeScore(b.comment_time_text) - buildTimeScore(a.comment_time_text) || b.priority_score - a.priority_score);
  buckets.threaded.sort((a, b) => (b.reply_count_estimate || 0) - (a.reply_count_estimate || 0) || b.priority_score - a.priority_score);
  buckets.fallback.sort((a, b) => b.priority_score - a.priority_score);

  const selected = [];
  const selectedKeys = new Set();
  const addFromBucket = (items, count, bucketName) => {
    for (const item of items) {
      if (selected.length >= limit || count <= 0) break;
      const key = `${item.author_name}\n${item.content}`;
      if (selectedKeys.has(key)) continue;
      selected.push({ ...item, sampling_bucket: bucketName });
      selectedKeys.add(key);
      count -= 1;
    }
  };

  addFromBucket(buckets.top_liked, Math.max(1, Math.round(limit * 0.4)), "top_liked");
  addFromBucket(buckets.latest, Math.max(1, Math.round(limit * 0.25)), "latest");
  addFromBucket(buckets.threaded, Math.max(1, Math.round(limit * 0.25)), "threaded");
  addFromBucket(buckets.fallback, limit - selected.length, "fallback");
  addFromBucket(buckets.top_liked, limit - selected.length, "top_liked");
  addFromBucket(buckets.latest, limit - selected.length, "latest");
  addFromBucket(buckets.threaded, limit - selected.length, "threaded");

  return {
    comments: selected,
    stats: {
      selectedTopLiked: selected.filter((item) => item.sampling_bucket === "top_liked").length,
      selectedLatest: selected.filter((item) => item.sampling_bucket === "latest").length,
      selectedThreaded: selected.filter((item) => item.sampling_bucket === "threaded").length,
      selectedFallback: selected.filter((item) => item.sampling_bucket === "fallback").length,
    },
  };
}

function dedupeComments(comments) {
  const seen = new Set();
  const output = [];
  let skippedNoise = 0;
  let skippedDuplicate = 0;
  for (const item of comments) {
    const authorName = String(item.author_name || "").trim();
    const content = String(item.content || "").trim();
    if (!content) continue;
    if (isNoiseComment(authorName, content)) continue;
    const normalizedContent = normalizeCommentContent(content);
    if (!normalizedContent) {
      skippedNoise += 1;
      continue;
    }
    if (isNoiseComment(authorName, normalizedContent)) {
      skippedNoise += 1;
      continue;
    }
    const key = `${authorName}\n${normalizedContent}`;
    if (seen.has(key)) {
      skippedDuplicate += 1;
      continue;
    }
    seen.add(key);
    const enriched = {
      ...item,
      author_name: authorName,
      content: normalizedContent,
      like_count: Number.isFinite(item.like_count) ? item.like_count : 0,
      comment_time_text: String(item.comment_time_text || "").trim(),
      has_replies: Boolean(item.has_replies),
      reply_count_estimate: Number.isFinite(item.reply_count_estimate) ? item.reply_count_estimate : 0,
    };
    enriched.priority_components = computePriorityComponents(enriched);
    enriched.priority_score = computePriorityScore(enriched);
    output.push({
      ...enriched,
    });
  }
  return {
    comments: output,
    stats: {
      skippedNoise,
      skippedDuplicate,
    },
  };
}

function isNoiseComment(authorName, content) {
  const normalized = content.replace(/\s+/g, " ").trim();
  if (!normalized) return true;

  const exactNoiseTexts = new Set([
    "同款",
    "查看全部评论",
    "展开更多评论",
  ]);
  if (exactNoiseTexts.has(normalized)) return true;

  const noisePatterns = [
    /^共\s*\d+\s*条评论$/,
    /^\d+\s*个笔记同款商品$/,
    /^登录后查看更多评论$/,
    /^打开小红书看全量评论$/,
  ];
  if (noisePatterns.some((pattern) => pattern.test(normalized))) return true;

  if (!authorName) {
    if (/^(赞|回复|分享|收藏)\s*\d*$/.test(normalized)) return true;
    if (normalized.length <= 2) return true;
  }

  return false;
}

function looksLikeLogin(url, text) {
  return (
    /login|passport|signin/i.test(url) ||
    /扫码登录|请先登录|验证码|登录后查看更多|登录以继续|短信验证码|继续访问/.test(text)
  );
}

async function readBodyText(page) {
  try {
    return await page.locator("body").innerText({ timeout: 2000 });
  } catch {
    return "";
  }
}

async function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function handlePossibleLogin(page, rl, loginWaitSeconds) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const currentUrl = page.url();
    const pageText = await readBodyText(page);
    if (!looksLikeLogin(currentUrl, pageText)) {
      return;
    }

    output.write("\n检测到可能需要登录或过验证。请在弹出的浏览器中完成操作。\n");
    if (process.stdin.isTTY) {
      await rl.question("登录完成后按 Enter 继续...");
    } else {
      output.write(`当前不是交互终端，将自动等待 ${loginWaitSeconds} 秒后继续。\n`);
      await wait(Math.max(5, loginWaitSeconds) * 1000);
    }
    await page.waitForTimeout(1500);
  }
}

async function waitForNoteSurface(page) {
  const selectors = ["#detail-title", "#detail-desc", ".note-content", ".comments-el", ".engage-bar"];
  for (let attempt = 0; attempt < 6; attempt += 1) {
    for (const selector of selectors) {
      try {
        await page.waitForSelector(selector, { timeout: 1500 });
        return true;
      } catch {}
    }
    await page.waitForTimeout(1000);
  }
  return false;
}

async function openCommentsArea(page) {
  const maybeButtons = [
    "text=评论",
    ".comments-el",
    ".comment-container",
    ".engage-bar",
    "[class*='comment']",
  ];
  for (const selector of maybeButtons) {
    try {
      const locator = page.locator(selector);
      if ((await locator.count()) > 0) {
        await locator.first().click({ force: true, timeout: 1200 });
        await page.waitForTimeout(600);
        return;
      }
    } catch {}
  }
}

async function expandReplyThreads(page) {
  const markExpandedReplyTarget = async (locator) => {
    try {
      await locator.evaluate((node) => {
        const text = (node.textContent || "").replace(/\s+/g, " ").trim();
        const match = text.match(/展开\s*(\d+)\s*条回复/);
        const expandedCount = match ? Number.parseInt(match[1], 10) : 1;
        const selectors = [
          ".parent-comment",
          ".comment-item",
          "[class*='parent-comment']",
          ".sub-comment-item",
          "[class*='commentItem']",
          "[class*='comment-item']",
          "[class*='comment-container']",
          "[class*='comment-list'] > div",
        ];
        let current = node instanceof HTMLElement ? node : null;
        while (current) {
          if (selectors.some((selector) => {
            try {
              return current.matches(selector);
            } catch {
              return false;
            }
          })) {
            const previous = Number.parseInt(current.getAttribute("data-codex-expanded-replies") || "0", 10);
            current.setAttribute("data-codex-expanded-flag", "1");
            current.setAttribute("data-codex-expanded-replies", String(Math.max(previous, expandedCount || 1)));
            break;
          }
          current = current.parentElement;
        }
      });
    } catch {}
  };

  const patterns = [
    /^展开\s*\d+\s*条回复$/,
    /^展开更多回复$/,
    /^查看全部回复$/,
    /^查看\s*\d+\s*条回复$/,
    /^更多回复$/,
    /^展开回复$/,
  ];

  for (let round = 0; round < 10; round += 1) {
    let clicked = 0;
    for (const pattern of patterns) {
      const locator = page.getByText(pattern, { exact: true });
      const count = await locator.count();
      for (let index = 0; index < count; index += 1) {
        if (clicked >= 20) break;
        const item = locator.nth(index);
        try {
          if (!(await item.isVisible())) continue;
          await item.scrollIntoViewIfNeeded({ timeout: 1000 });
          await markExpandedReplyTarget(item);
          await item.click({ force: true, timeout: 1200 });
          clicked += 1;
          await page.waitForTimeout(250);
        } catch {}
      }
      if (clicked >= 20) break;
    }

    if (!clicked) break;
    await page.waitForTimeout(800);
  }
}

async function measureCommentProgress(page) {
  return page.evaluate((selector) => {
    const markerAttr = "data-codex-comment-scroll-root";
    const clearMarkers = () => {
      for (const node of document.querySelectorAll(`[${markerAttr}]`)) {
        node.removeAttribute(markerAttr);
      }
    };
    const isScrollable = (node) => {
      if (!(node instanceof HTMLElement)) return false;
      const style = window.getComputedStyle(node);
      const overflowY = style.overflowY || "";
      const canScroll = /(auto|scroll|overlay)/i.test(overflowY);
      return node.scrollHeight > node.clientHeight + 40 && (canScroll || node.scrollHeight - node.clientHeight > 200);
    };
    const chooseScrollRoot = (candidates) => {
      const scored = [];
      for (const candidate of candidates) {
        let current = candidate instanceof HTMLElement ? candidate : null;
        let depth = 0;
        while (current && depth < 8) {
          if (isScrollable(current)) {
            scored.push(current);
          }
          current = current.parentElement;
          depth += 1;
        }
      }
      const unique = Array.from(new Set(scored));
      unique.sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight));
      return unique[0] || null;
    };

    const candidates = Array.from(document.querySelectorAll(selector));
    const textNodes = Array.from(document.querySelectorAll("span, button, div"));
    const expandPatterns = [
      /^展开\s*\d+\s*条回复$/,
      /^展开更多回复$/,
      /^查看全部回复$/,
      /^查看\s*\d+\s*条回复$/,
      /^更多回复$/,
      /^展开回复$/,
    ];
    const pendingExpandCount = textNodes.filter((node) => {
      const text = (node.textContent || "").replace(/\s+/g, " ").trim();
      if (!text || !expandPatterns.some((pattern) => pattern.test(text))) return false;
      const rect = node.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    }).length;
    clearMarkers();
    const commentScrollRoot = chooseScrollRoot(candidates);
    if (commentScrollRoot) {
      commentScrollRoot.setAttribute(markerAttr, "1");
    }
    const scrollingElement = commentScrollRoot || document.scrollingElement || document.documentElement;
    return {
      candidateCount: candidates.length,
      pendingExpandCount,
      scrollTop: scrollingElement.scrollTop || window.scrollY || 0,
      clientHeight: scrollingElement.clientHeight || window.innerHeight || 0,
      scrollHeight: scrollingElement.scrollHeight || document.body.scrollHeight || 0,
      scrollSource: commentScrollRoot ? "container" : "window",
    };
  }, COMMENT_CANDIDATE_SELECTOR);
}

function formatProgress(progress) {
  return `comments=${progress.candidateCount} pending_expands=${progress.pendingExpandCount} scroll=${Math.round(progress.scrollTop)}/${Math.round(progress.scrollHeight)} source=${progress.scrollSource}`;
}

async function scrollCommentViewport(page, deltaY) {
  await page.evaluate((amount) => {
    const markerAttr = "data-codex-comment-scroll-root";
    const target = document.querySelector(`[${markerAttr}]`);
    if (target instanceof HTMLElement) {
      target.scrollBy({ top: amount, behavior: "instant" });
      return;
    }
    window.scrollBy(0, amount);
  }, deltaY);
}

async function scrollComments(page, targetCount) {
  await openCommentsArea(page);
  let bestCount = 0;
  let stagnantRounds = 0;
  let lowMovementRounds = 0;
  let lastScrollTop = 0;
  for (let i = 0; i < 80; i += 1) {
    await expandReplyThreads(page);
    const progressBefore = await measureCommentProgress(page);
    bestCount = Math.max(bestCount, progressBefore.candidateCount);
    output.write(`  [round ${i + 1}] before ${formatProgress(progressBefore)} best=${bestCount}\n`);
    if (bestCount >= targetCount) break;

    try {
      await page.mouse.wheel(0, 900);
    } catch {}
    try {
      await scrollCommentViewport(page, 900);
    } catch {}
    await page.waitForTimeout(850);
    await expandReplyThreads(page);
    const progressAfter = await measureCommentProgress(page);
    const scrollDelta = Math.abs((progressAfter.scrollTop || 0) - lastScrollTop);
    lastScrollTop = progressAfter.scrollTop || 0;
    if (progressAfter.candidateCount > bestCount) {
      bestCount = progressAfter.candidateCount;
      stagnantRounds = 0;
    } else if (progressAfter.pendingExpandCount > 0) {
      stagnantRounds = 0;
    } else {
      stagnantRounds += 1;
    }
    if (scrollDelta < 80) {
      lowMovementRounds += 1;
    } else {
      lowMovementRounds = 0;
    }

    const nearBottom = progressAfter.scrollHeight - progressAfter.scrollTop - progressAfter.clientHeight < 180;
    output.write(
      `  [round ${i + 1}] after ${formatProgress(progressAfter)} best=${bestCount} stagnant=${stagnantRounds} low_movement=${lowMovementRounds} near_bottom=${nearBottom}\n`,
    );
    if (bestCount >= targetCount) break;
    if (nearBottom && stagnantRounds >= 4) break;
    if (nearBottom && lowMovementRounds >= 3) break;
    if (lowMovementRounds >= 10 && stagnantRounds >= 10) break;
  }
  await expandReplyThreads(page);
}

async function extractComments(page, commentLimit) {
  return page.evaluate(({ selector }) => {
    const textOf = (el) => (el?.textContent || "").replace(/\s+/g, " ").trim();
    const parseCount = (value) => {
      const text = String(value || "").trim().toLowerCase();
      if (!text) return 0;
      const match = text.match(/(\d+(?:\.\d+)?)/);
      if (!match) return 0;
      let number = Number.parseFloat(match[1]);
      if (!Number.isFinite(number)) return 0;
      if (text.includes("万") || text.endsWith("w")) number *= 10000;
      if (text.includes("千") || text.endsWith("k")) number *= 1000;
      return Math.trunc(number);
    };
    const parseReplyCount = (text) => {
      const match = String(text || "").match(/展开\s*(\d+)\s*条回复/);
      return match ? Number.parseInt(match[1], 10) : 0;
    };
    const splitTimeAndLocation = (rawText) => {
      const text = String(rawText || "").trim();
      if (!text) return { comment_time_text: "", comment_location_text: "" };
      const patterns = [
        /^(刚刚|今天|昨天|前天)(.*)$/,
        /^(\d+\s*分钟前)(.*)$/,
        /^(\d+\s*小时前)(.*)$/,
        /^(\d+\s*天前)(.*)$/,
        /^(\d{4}-\d{2}-\d{2})(.*)$/,
        /^(\d{2}-\d{2})(.*)$/,
      ];
      for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match) {
          return {
            comment_time_text: String(match[1] || "").trim(),
            comment_location_text: String(match[2] || "").trim(),
          };
        }
      }
      return { comment_time_text: text, comment_location_text: "" };
    };
    const stripMetaNodes = (root) => {
      if (!root) return root;
      for (const selector of [
        ".name",
        ".username",
        "[class*='author']",
        ".count",
        "[class*='like']",
        "[class*='time']",
        "[class*='date']",
        "[class*='location']",
        "[class*='reply']",
        "[class*='more']",
        "[class*='expand']",
        "[class*='action']",
        "button",
      ]) {
        for (const node of root.querySelectorAll(selector)) {
          node.remove();
        }
      }
      return root;
    };
    const candidates = Array.from(
      document.querySelectorAll(
        selector,
      ),
    );

    const results = [];
    let extractedCount = 0;
    for (let index = 0; index < candidates.length; index += 1) {
      const el = candidates[index];
      const author =
        textOf(el.querySelector(".name")) ||
        textOf(el.querySelector(".username")) ||
        textOf(el.querySelector("[class*='author']")) ||
        "";
      const wholeTextBeforeStrip = textOf(el);

      const timeTextRaw =
        textOf(el.querySelector("[class*='time']")) ||
        textOf(el.querySelector("[class*='date']")) ||
        "";
      const meta = splitTimeAndLocation(timeTextRaw);

      const clone = stripMetaNodes(el.cloneNode(true));
      let content =
        textOf(clone.querySelector(".content")) ||
        textOf(clone.querySelector("[class*='content']")) ||
        textOf(clone.querySelector("[class*='comment-text']")) ||
        textOf(clone.querySelector("[class*='text']")) ||
        "";

      const likeText =
        textOf(el.querySelector(".count")) ||
        textOf(el.querySelector("[class*='like'] .count")) ||
        "0";
      const likeCount = (() => {
        const text = likeText.toLowerCase();
        const match = text.match(/(\d+(?:\.\d+)?)/);
        if (!match) return 0;
        let number = Number.parseFloat(match[1]);
        if (!Number.isFinite(number)) return 0;
        if (text.includes("万") || text.endsWith("w")) number *= 10000;
        if (text.includes("千") || text.endsWith("k")) number *= 1000;
        return Math.trunc(number);
      })();
      const replyCountText =
        textOf(el.querySelector(".reply.icon-container .count")) ||
        textOf(el.querySelector(".reply.icon-container span")) ||
        textOf(el.querySelector("[class*='reply'] .count")) ||
        "";
      const replyCountFromNode = parseCount(replyCountText);
      const replyTriggerTexts = Array.from(el.querySelectorAll("span, button, div, a"))
        .map((node) => textOf(node))
        .filter((value) => /展开\s*\d+\s*条回复|展开更多回复|查看全部回复|更多回复|回复\s*@|作者回复/.test(value));
      const markedExpandedCount = Number.parseInt(el.getAttribute("data-codex-expanded-replies") || "0", 10);
      const replyCountEstimate = Math.max(
        0,
        replyCountFromNode,
        markedExpandedCount,
        ...replyTriggerTexts.map((value) => parseReplyCount(value)),
      );
      const nestedReplyCount = el.querySelectorAll(".sub-comment-item, [class*='subComment'], [class*='reply-item']").length;
      const nestedCandidateReplyCount = Math.max(0, el.querySelectorAll(selector).length - 1);
      const expandedFlag = el.getAttribute("data-codex-expanded-flag") === "1";
      const hasReplies =
        replyCountEstimate > 0 ||
        nestedReplyCount > 0 ||
        nestedCandidateReplyCount > 0 ||
        expandedFlag ||
        replyTriggerTexts.length > 0 ||
        /回复\s*@|作者回复/.test(wholeTextBeforeStrip);

      if (!content) {
        const wholeText = textOf(clone);
        content = wholeText.replace(author, "").replace(likeText, "").replace(timeTextRaw, "").trim().slice(0, 180);
      }

      content = content
        .replace(/展开\s*\d+\s*条回复/g, " ")
        .replace(/展开\s*\d+\s*条回答/g, " ")
        .replace(/(?:查看全部回复|展开更多回复|展开更多评论|更多回复)/g, " ")
        .replace(/(?:查看全部回答|展开更多回答|更多回答|展开回答|展开回复)/g, " ")
        .replace(/\s+/g, " ")
        .trim();

      if (!content) continue;
      extractedCount += 1;
      results.push({
        author_name: author,
        content,
        like_count: Number.isFinite(likeCount) ? likeCount : 0,
        comment_time_text: meta.comment_time_text,
        comment_location_text: meta.comment_location_text,
        has_replies: Boolean(hasReplies),
        reply_count_estimate:
          Number.isFinite(replyCountEstimate) && replyCountEstimate > 0
            ? replyCountEstimate
            : (nestedReplyCount > 0 ? nestedReplyCount : (nestedCandidateReplyCount > 0 ? nestedCandidateReplyCount : (expandedFlag ? 1 : 0))),
        capture_rank: index + 1,
      });
    }
    return {
      candidateCount: candidates.length,
      extractedCount,
      comments: results,
    };
  }, { selector: COMMENT_CANDIDATE_SELECTOR });
}

async function closeOverlay(page) {
  const selectors = [".close-box", ".close-circle", "[aria-label='关闭']", ".note-detail-mask .close"];
  for (const selector of selectors) {
    try {
      const locator = page.locator(selector);
      if ((await locator.count()) > 0) {
        await locator.first().click({ force: true, timeout: 1000 });
        await page.waitForTimeout(400);
        return;
      }
    } catch {}
  }
  try {
    await page.keyboard.press("Escape");
  } catch {}
}

function flushPosts(outputPath, posts) {
  fs.writeFileSync(outputPath, JSON.stringify({ posts }, null, 2), "utf-8");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const raw = JSON.parse(fs.readFileSync(args.input, "utf-8"));
  const posts = Array.isArray(raw.posts) ? raw.posts : [];
  const rawCommentStore = loadRawCommentStore(args.rawCommentsFile);

  const { chromium } = await import("playwright");
  fs.mkdirSync(args.userDataDir, { recursive: true });

  const context = await chromium.launchPersistentContext(args.userDataDir, {
    headless: args.headless,
    viewport: { width: 1440, height: 980 },
    args: ["--disable-crashpad", "--disable-crash-reporter", "--disable-breakpad"],
  });

  const page = context.pages()[0] || (await context.newPage());
  const rl = readline.createInterface({ input, output });

  let processed = 0;
  try {
    for (const post of posts) {
      if (!post || typeof post !== "object") continue;
      if (args.postId && String(post.post_id || "") !== args.postId) continue;
      if (args.limit !== null && processed >= args.limit) break;
      ensureCommentDefaults(post);
      if (args.resume && hasFetchedComments(post)) {
        output.write(`\n跳过已抓取帖子：${post.source_url || post.post_id || "unknown"}\n`);
        continue;
      }

      const sourceUrl = String(post.source_url || "");
      if (!sourceUrl) continue;

      output.write(`\n打开帖子：${sourceUrl}\n`);
      await page.goto(sourceUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
      await page.waitForTimeout(2500);

      await handlePossibleLogin(page, rl, args.loginWaitSeconds);
      await waitForNoteSurface(page);
      if (!String(post.page_screenshot_url || "").trim()) {
        const screenshotUrl = await capturePostFallbackScreenshot(page, args.output, post.post_id);
        if (screenshotUrl) {
          post.page_screenshot_url = screenshotUrl;
        }
      }
      const normalizedCommentLimit = normalizeCommentLimit(args.commentLimit);
      const expectedCommentCount = Number.isFinite(Number(post.comment_count)) ? Number(post.comment_count) : 0;
      const targetCount = Math.min(
        normalizedCommentLimit,
        expectedCommentCount > 0 ? expectedCommentCount : normalizedCommentLimit,
      );

      await scrollComments(page, targetCount);

      const extraction = await extractComments(page, normalizedCommentLimit);
      const deduped = dedupeComments(extraction.comments);
      const prioritized = prioritizeComments(deduped.comments, normalizedCommentLimit);
      const comments = prioritized.comments;
      post.comment_sample_count = comments.length;
      post.comment_fetch_status = comments.length > 0 ? "done" : "unavailable";
      delete post.raw_comments;

      const postId = String(post.post_id || "");
      if (postId) {
        rawCommentStore.posts[postId] = {
          post_id: postId,
          source_url: sourceUrl,
          comment_sample_count: comments.length,
          comment_fetch_status: post.comment_fetch_status,
          raw_comments: comments,
        };
      }

      output.write(
        `评论统计：候选节点 ${extraction.candidateCount} -> 提取到正文 ${extraction.extractedCount} -> 去重后 ${deduped.comments.length} -> 最终保留 ${comments.length}（noise=${deduped.stats.skippedNoise} duplicate=${deduped.stats.skippedDuplicate} top_liked=${prioritized.stats.selectedTopLiked} latest=${prioritized.stats.selectedLatest} threaded=${prioritized.stats.selectedThreaded} fallback=${prioritized.stats.selectedFallback}）\n`,
      );
      flushPosts(args.output, posts);
      writeRawCommentStore(args.rawCommentsFile, rawCommentStore);
      processed += 1;
      await closeOverlay(page);
      await page.waitForTimeout(500);
    }
  } finally {
    rl.close();
    await context.close();
  }

  flushPosts(args.output, posts);
  writeRawCommentStore(args.rawCommentsFile, rawCommentStore);
  output.write(`\n写入完成：${args.output}\n`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
