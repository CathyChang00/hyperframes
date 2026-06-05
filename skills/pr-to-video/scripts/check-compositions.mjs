#!/usr/bin/env node
// check-compositions.mjs — Step 7 finalize 预飞 harness
//
// 跑在 Step 6 worker 全部返回后、Step 7 finalize 开始拼 index.html 之前。
// 拦历史 worker bug（finalize 平均花 13 分钟 edit-and-retry 排查）：
//
//   1. Wrapper-ancestor selector —— CSS / JS selector 写成 `.<scene-id>-root .foo`
//      / `.<scene-id>-root #foo`。preview / snapshot OK（bundler 保留 wrapper），
//      但 `hyperframes render` 走的 producer 管线会**剥掉** wrapper，selector
//      全部失配 → scene 渲成黑屏或裸 DOM。正确写法：裸的 `.s<N>-foo` / `#s<N>-foo`，
//      runtime scoper 自动加 host scope。
//   2. Self data-composition-id selector —— CSS 写成
//      `[data-composition-id="<scene-id>"] { ... }` 会触发新版 CLI
//      `composition_self_attribute_selector` warning。root 样式应写 `#root`。
//   3. Scene-root id selector —— `#<scene-id>-root` 不是 runtime contract。
//      root 只能用 `#root`；scene 内部元素用 `#s<N>-foo`。
//   4. Root contract 缺 —— 没 `id="root"`、没 `class="<scene-id>-root"`、没
//      `data-composition-id`、没 `data-duration`、没 `window.__timelines[...]`。
//   5. Asset 引用了 <project-root>/public/ 里不存在的文件 —— worker 编造或拼写错
//      了 basename。
//
// Usage:
//   node check-compositions.mjs --hyperframes . --group-spec ./group_spec.json
//
// 退出码：
//   0 = 所有 composition 过检。stdout 给汇总。
//   1 = ≥1 fatal 违规。stderr 列 per-scene per-rule 失败项；编排器应该重派受
//       影响的 worker，不在 finalize 里 patch。

import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const argv = process.argv.slice(2);
const flag = (name, def) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && i + 1 < argv.length ? argv[i + 1] : def;
};
const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const hyperframesDir = resolve(flag("hyperframes", "."));
const groupSpecPath = resolve(flag("group-spec", "./group_spec.json"));
const compositionsDir = join(hyperframesDir, "compositions");

if (!existsSync(groupSpecPath)) {
  console.error(`✗ group_spec.json not found at ${groupSpecPath}`);
  process.exit(1);
}
if (!existsSync(compositionsDir)) {
  console.error(`✗ compositions dir not found at ${compositionsDir}`);
  process.exit(1);
}

const groupSpec = JSON.parse(readFileSync(groupSpecPath, "utf8"));
const sceneIds = (groupSpec.groups || []).flatMap((g) => g.scene_ids || []);

if (sceneIds.length === 0) {
  console.error(`✗ no scene_ids found in group_spec.json`);
  process.exit(1);
}

// scene_id → group entry (for component-meta lookup)
const sceneEntries = new Map();
for (const g of groupSpec.groups || []) {
  for (const sid of g.scene_ids || []) {
    sceneEntries.set(sid, g.scenes?.[sid] || {});
  }
}

const visualTargets =
  Array.isArray(groupSpec.visual_clips) && groupSpec.visual_clips.length > 0
    ? groupSpec.visual_clips.map((v) => ({
        id: String(v.id || ""),
        file: String(v.file || `compositions/${v.id}.html`),
        kind: v.kind || "scene",
        sceneIds: Array.isArray(v.scene_ids) ? v.scene_ids : [],
      }))
    : sceneIds.map((sid) => ({
        id: sid,
        file: `compositions/${sid}.html`,
        kind: "scene",
        sceneIds: [sid],
      }));

if (visualTargets.length === 0) {
  console.error(`✗ no visual clips found in group_spec.json`);
  process.exit(1);
}

// Component metadata lookup — chunks/index.json carries rank / forbidden_with /
// trigger_signals / visual_role per component (written by emit-chunks.mjs).
// Keyed by component id, which equals the html file's basename. Empty when the
// preset hasn't migrated to the new schema; rank checks then silently skip.
const componentMeta = new Map();
{
  // Resolve chunks/index.json off the first scene's design_chunks.tokens_file —
  // tokens_file is required by prep.mjs so it's always present when chunks were
  // emitted. Walk up from chunks/tokens.css → chunks/ → chunks/index.json.
  const anyScene = [...sceneEntries.values()].find((e) => e.design_chunks?.tokens_file);
  const tokensPath = anyScene?.design_chunks?.tokens_file;
  if (tokensPath) {
    const chunksDir = dirname(tokensPath);
    const indexPath = join(chunksDir, "index.json");
    if (existsSync(indexPath)) {
      try {
        const index = JSON.parse(readFileSync(indexPath, "utf8"));
        for (const c of index.components || []) {
          componentMeta.set(c.id, {
            rank: c.rank ?? null,
            trigger_signals: c.trigger_signals || [],
            forbidden_with: c.forbidden_with || [],
            visual_role: c.visual_role || null,
          });
        }
      } catch {
        // Malformed index.json — skip metadata-driven checks; let other gates flag the data issue
      }
    }
  }
}

// Given an absolute path like "/.../chunks/components/hero.html", return the
// component id "hero". Returns null if path doesn't fit the expected shape so
// callers can skip safely.
function componentIdFromPath(absPath) {
  if (typeof absPath !== "string") return null;
  const m = absPath.match(/\/chunks\/components\/([a-z0-9-]+)\.html$/);
  return m ? m[1] : null;
}

const errors = []; // fatal: { sceneId, rule, detail }
const anomalies = []; // non-fatal: { sceneId, rule, detail }

for (const target of visualTargets) {
  const sceneId = target.id;
  const compRel = target.file || `compositions/${sceneId}.html`;
  const filePath = join(hyperframesDir, compRel);

  // Rule 0: 文件存在且非空
  if (!existsSync(filePath) || statSync(filePath).size === 0) {
    errors.push({
      sceneId,
      rule: "file",
      detail: `${compRel} missing or empty`,
    });
    continue; // 这个 scene 后面规则跳过
  }

  const html = readFileSync(filePath, "utf8");

  // Rule 1: root div 契约
  // 必须有且仅有一个 root div，同时带 id="root" 和 class="<scene-id>-root"
  const rootDivRe = new RegExp(
    `<div\\b[^>]*\\bid=["']root["'][^>]*\\bclass=["'][^"']*\\b${sceneId}-root\\b[^"']*["']`,
    "i",
  );
  const rootDivAltRe = new RegExp(
    `<div\\b[^>]*\\bclass=["'][^"']*\\b${sceneId}-root\\b[^"']*["'][^>]*\\bid=["']root["']`,
    "i",
  );
  if (!rootDivRe.test(html) && !rootDivAltRe.test(html)) {
    errors.push({
      sceneId,
      rule: "root-contract",
      detail: `no <div id="root" class="${sceneId}-root" ...> found — 必须同 div 上同时有这两个属性`,
    });
  }

  // Rule 1b: root 上的 data-composition-id 和 data-duration
  const hostIdRe = new RegExp(`data-composition-id=["']${sceneId}["']`);
  if (!hostIdRe.test(html)) {
    errors.push({
      sceneId,
      rule: "data-composition-id",
      detail: `no data-composition-id="${sceneId}" found`,
    });
  }
  if (!/data-duration=["'][\d.]+["']/.test(html)) {
    errors.push({
      sceneId,
      rule: "data-duration",
      detail: `no data-duration="<float>" found on root`,
    });
  }

  // Rule 1c: window.__timelines["<scene-id>"] 注册
  const tlKeyRe = new RegExp(`window\\.__timelines\\s*\\[\\s*["']${sceneId}["']\\s*\\]\\s*=`);
  if (!tlKeyRe.test(html)) {
    errors.push({
      sceneId,
      rule: "timeline-registration",
      detail: `no window.__timelines["${sceneId}"] = ... line found (scene id 必须原文)`,
    });
  }

  // 推荐的命名空间前缀：scene_1 → s1-；group_w2 → g2- for shared nodes.
  // 用于 fix 提示 + 命名空间健康度检查。
  const groupM = sceneId.match(/^group_w(\d+)$/);
  const m = sceneId.match(/(\d+)/);
  const sN = groupM ? `g${groupM[1]}-` : m ? `s${m[1]}-` : `s-`;
  const sceneLocalHints =
    groupM && target.sceneIds.length
      ? `；logical-scene-only nodes may use ${target.sceneIds
          .map((sid) => `.${sid.replace(/^scene_/, "s")}-foo`)
          .join(" / ")}`
      : "";
  const wrapperAncestor = `.${sceneId}-root`; // bug 形态字面值
  const fixHint = `裸 .${sN}foo / #${sN}foo（不挂任何祖先）${sceneLocalHints}`;

  // Rule 2: CSS —— <style> 里不能有 wrapper-ancestor selector
  //
  // `.<scene-id>-root .foo` / `.<scene-id>-root #foo` 形态：preview / snapshot 走
  // bundler 路径会保留 wrapper element，所以 selector OK；但 `hyperframes render`
  // 走 producer 路径，会**剥掉** wrapper，selector 全部失配 → scene 渲成黑屏。
  // 历史 bug：product-launch-video 早期 worker prompt 教 agent 这么写。
  //
  // root 样式写 `#root { ... }`。compiler 会把 authored root id 改写成
  // instance-safe selector；不要写 `[data-composition-id="<scene-id>"]`，
  // 否则 `npx hyperframes lint` 会报 composition_self_attribute_selector。
  //
  // 同时禁 id selector `#<scene-id>-root`：这不是 runtime contract；内部元素
  // 用 `#s<N>-foo`。
  const styleBlocks = [...html.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/gi)];
  for (const sb of styleBlocks) {
    const css = sb[1];
    const stripped = css.replace(/\/\*[\s\S]*?\*\//g, "");

    // 2a: wrapper-ancestor selector（`.<scene-id>-root` 后跟空白/`>`/`+`/`~`/`,`/`.`/`#`）
    const escapedSceneId = escapeRegExp(sceneId);
    const wrapperRe = new RegExp(`\\.${escapedSceneId}-root(?=[\\s>+~,.#:\\[])`, "g");
    const wrapperHits = [...stripped.matchAll(wrapperRe)];
    if (wrapperHits.length > 0) {
      errors.push({
        sceneId,
        rule: "css-wrapper-ancestor",
        detail: `<style> 用 ${wrapperAncestor} 作祖先选择器（${wrapperHits.length} 处）— producer 渲染时这层 wrapper 会被剥掉，selector 全部失配。改成${fixHint}；root 元素自身的 token / 背景 / 字体写到 #root { ... }`,
      });
    }

    // 2b: self data-composition-id selector 会触发 CLI warning；root 样式用 #root。
    const selfAttrRe = new RegExp(
      `\\[\\s*data-composition-id\\s*=\\s*["']${escapedSceneId}["']\\s*\\]`,
      "g",
    );
    const selfAttrHits = [...stripped.matchAll(selfAttrRe)];
    if (selfAttrHits.length > 0) {
      errors.push({
        sceneId,
        rule: "css-self-composition-selector",
        detail: `<style> 用了 [data-composition-id="${sceneId}"] selector（${selfAttrHits.length} 处）— 会触发 npx hyperframes lint 的 composition_self_attribute_selector warning。root 样式改 #root { ... }；内部元素写 .${sN}foo / #${sN}foo`,
      });
    }

    // 2c: 禁 `#<scene-id>-root`，允许 `#root`。
    const idSelectors = [...stripped.matchAll(/(^|[\s,>+~])#([a-zA-Z][\w-]*)/gm)];
    const banned = idSelectors.map((sm) => sm[2]).filter((id) => id === `${sceneId}-root`);
    if (banned.length > 0) {
      errors.push({
        sceneId,
        rule: "css-scene-root-id-selector",
        detail: `<style> 用了禁用的 id selector：${[...new Set(banned)].map((b) => `#${b}`).join(", ")} — root 只能写 #root；内部元素改成${fixHint}`,
      });
    }
  }

  // Rule 3: JS —— <script> 里不能有 wrapper-ancestor selector / #<scene-id>-root
  const scriptBlocks = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)];
  for (const sb of scriptBlocks) {
    const js = sb[1];
    const stripped = js.replace(/\/\/[^\n]*/g, "").replace(/\/\*[\s\S]*?\*\//g, "");

    // 3a: 字符串字面值里含 `.<scene-id>-root` 当祖先
    const wrapperJsRe = new RegExp(
      `["'\`][^"'\`]*\\.${escapeRegExp(sceneId)}-root[\\s>+~,.#:\\[][^"'\`]*["'\`]`,
      "g",
    );
    const wrapperJsHits = [...stripped.matchAll(wrapperJsRe)];
    if (wrapperJsHits.length > 0) {
      errors.push({
        sceneId,
        rule: "js-wrapper-ancestor",
        detail: `<script> 字符串含 ${wrapperAncestor} 祖先 selector：${wrapperJsHits
          .slice(0, 3)
          .map((mm) => mm[0])
          .join(
            ", ",
          )}${wrapperJsHits.length > 3 ? ` (+${wrapperJsHits.length - 3} more)` : ""} — producer 渲染时 wrapper 会被剥掉。改成${fixHint}`,
      });
    }

    // 3b: 字符串字面值里含 `#<scene-id>-root`
    const bannedJsRe = new RegExp(
      `["'\`][^"'\`]*#${escapeRegExp(sceneId)}-root\\b[^"'\`]*["'\`]`,
      "g",
    );
    const matches = [...stripped.matchAll(bannedJsRe)];
    if (matches.length > 0) {
      errors.push({
        sceneId,
        rule: "js-scene-root-id-selector",
        detail: `<script> 含禁用 selector：${matches
          .slice(0, 3)
          .map((mm) => mm[0])
          .join(
            ", ",
          )}${matches.length > 3 ? ` (+${matches.length - 3} more)` : ""} — 改成${fixHint}`,
      });
    }

    // 3c: getElementById("<scene-id>-root")
    const banGEI = new RegExp(
      `getElementById\\(\\s*["'\`]${escapeRegExp(sceneId)}-root["'\`]\\s*\\)`,
      "g",
    );
    const geiMatches = [...stripped.matchAll(banGEI)];
    if (geiMatches.length > 0) {
      errors.push({
        sceneId,
        rule: "js-scene-root-id-selector",
        detail: `<script> 用了 ${geiMatches[0][0]} — 改用 document.querySelector("#root") 或 document.querySelector("#${sN}foo")`,
      });
    }
  }

  // Rule 4: 引用的 public/ asset 必须真存在
  const assetRefs = new Set();
  for (const m of html.matchAll(/\bpublic\/[A-Za-z0-9._/-]+/g)) {
    assetRefs.add(m[0]);
  }
  for (const ref of assetRefs) {
    if (!existsSync(join(hyperframesDir, ref))) {
      errors.push({
        sceneId,
        rule: "asset",
        detail: `引用了 "${ref}" 但 project-root/public/ 里没这个文件`,
      });
    }
  }

  // Rule 5: forbidden pattern（CSS animation、Date.now() 等）
  const forbidden = [
    { re: /\btransition\s*:/i, name: "CSS transition:", scope: "style" },
    { re: /\banimation\s*:/i, name: "CSS animation:", scope: "style" },
    {
      re: /@font-face\b/i,
      name: "@font-face（在 index.html 声明，不在 scene 里）",
      scope: "style",
    },
    { re: /\bDate\.now\b/, name: "Date.now()", scope: "script" },
    { re: /\bMath\.random\b/, name: "Math.random()", scope: "script" },
    { re: /\bperformance\.now\b/, name: "performance.now()", scope: "script" },
    { re: /\brepeat\s*:\s*-1\b/, name: "repeat: -1", scope: "script" },
    { re: /\bfetch\s*\(/, name: "fetch(", scope: "script" },
  ];

  // CSS transition:/animation: and @font-face are PLV pre-flight conventions
  // (force all motion through one seekable GSAP timeline; declare fonts once in
  // index.html <head>), NOT hyperframes-core contract — core/determinism-rules.md
  // forbids none of them and adapters/css-animations.md actually supports seekable
  // CSS keyframes. Date.now/Math.random/performance.now/repeat:-1/fetch ARE core
  // determinism rules. The detail string says which so the agent doesn't go
  // cross-checking core for a rule that isn't there.
  const plvOnly = new Set(["CSS transition:", "CSS animation:"]);
  for (const f of forbidden) {
    const blocks = f.scope === "style" ? styleBlocks : scriptBlocks;
    for (const m of blocks) {
      if (f.re.test(m[1])) {
        const src = plvOnly.has(f.name)
          ? "PLV pre-flight 约束（强制改成 GSAP tween；非 core 契约，css-animations adapter 本身支持可 seek CSS）"
          : f.name.startsWith("@font-face")
            ? "PLV 约束（@font-face 移到 index.html <head>）"
            : "core 确定性契约";
        errors.push({
          sceneId,
          rule: "forbidden",
          detail: `<${f.scope}> 里出现 ${f.name} — ${src}`,
        });
        break;
      }
    }
  }

  // Rule 6: asset 路径不能有前导斜杠
  if (/\bsrc=["']\/public\//.test(html) || /\burl\(["']?\/public\//.test(html)) {
    errors.push({
      sceneId,
      rule: "asset-path",
      detail: `asset 引用用了前导斜杠 "/public/..." — 必须 "public/..."（无前导斜杠）`,
    });
  }

  // Rule 6b: 注释里禁止字面 HTML 开标签
  // `npx hyperframes lint` 用正则扫 <template> / <style> / <script>，注释里写字面标签会被当成真标签 → 误报结构错。
  // 在预飞阶段拦住，省掉 finalize 90s 的 lint debug 循环。
  if (/<!--[^>]*<(template|style|script)[> ][^>]*-->/.test(html)) {
    errors.push({
      sceneId,
      rule: "literal-tag-in-comment",
      detail: `注释里有字面 <template>/<style>/<script> — 会污染 npx hyperframes lint 的正则扫描；把 < 转义成 &lt; 或改成纯文本描述`,
    });
  }
}

for (const logicalSceneId of sceneIds) {
  const entry = sceneEntries.get(logicalSceneId) || {};

  // Rule 7 (fatal once metadata is present)：rank-1 唯一性 + forbidden_with 冲突
  //
  // 来源 = design-system/chunks/index.json.components[].{rank, forbidden_with}（由
  // emit-chunks.mjs 写出，最初由 preset components/<id>.md 的 YAML frontmatter 声明）。
  // 旧 preset 没有 frontmatter → componentMeta 为空 → 这条规则自动跳过；不破坏向后兼容。
  if (componentMeta.size === 0) continue;
  const cited = (entry.design_chunks?.components || []).map(componentIdFromPath).filter(Boolean);

  const rank1 = cited.filter((id) => componentMeta.get(id)?.rank === 1);
  if (rank1.length > 1) {
    errors.push({
      sceneId: logicalSceneId,
      rule: "rank-1-overload",
      detail: `scene declares ${rank1.length} focal (rank=1) components: [${rank1.join(", ")}] — at most 1 rank-1 element per scene. Split into separate scenes or downgrade one to rank=2 (supporting) / rank=3 (chrome).`,
    });
  }

  const citedSet = new Set(cited);
  for (const id of cited) {
    const meta = componentMeta.get(id);
    if (!meta) continue;
    for (const forbidden of meta.forbidden_with) {
      if (citedSet.has(forbidden) && id < forbidden) {
        errors.push({
          sceneId: logicalSceneId,
          rule: "forbidden-with",
          detail: `scene cites components "${id}" and "${forbidden}" together — preset declares them mutually exclusive (forbidden_with). Drop one.`,
        });
      }
    }
  }
}

// ---------- 汇报 ----------
const anomalyByScene = new Map();
for (const a of anomalies) {
  if (!anomalyByScene.has(a.sceneId)) anomalyByScene.set(a.sceneId, []);
  anomalyByScene.get(a.sceneId).push(a);
}

if (errors.length === 0) {
  console.log(
    `✓ all ${visualTargets.length} visual composition(s) for ${sceneIds.length} logical scene(s) pass pre-finalize checks`,
  );
  if (anomalies.length > 0) {
    console.log(`\nanomalies (non-fatal):`);
    for (const [sid, list] of anomalyByScene) {
      console.log(`  ${sid}:`);
      for (const a of list) console.log(`    [${a.rule}] ${a.detail}`);
    }
  }
  process.exit(0);
}

// 按 sceneId 分组方便看
const bySceneId = new Map();
for (const e of errors) {
  if (!bySceneId.has(e.sceneId)) bySceneId.set(e.sceneId, []);
  bySceneId.get(e.sceneId).push(e);
}

console.error(`✗ ${errors.length} 个 fatal 违规 跨 ${bySceneId.size} 个 composition/scene id：\n`);
for (const [sceneId, list] of bySceneId) {
  console.error(`  ${sceneId}:`);
  for (const e of list) {
    console.error(`    [${e.rule}] ${e.detail}`);
  }
}
if (anomalies.length > 0) {
  console.error(`\nanomalies (non-fatal)：`);
  for (const [sid, list] of anomalyByScene) {
    console.error(`  ${sid}:`);
    for (const a of list) console.error(`    [${a.rule}] ${a.detail}`);
  }
}
console.error(`\n  修对应 visual HTML（或让编排器重派 worker）后再跑 finalize。`);
process.exit(1);
