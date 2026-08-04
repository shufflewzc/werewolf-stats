#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const childProcess = require("child_process");

const ROOT = path.resolve(__dirname, "..");
const MINIPROGRAM_DIR = path.join(ROOT, "miniprogram");
const EXPECTED_APPID = "wx6299309f1691bf3e";
const EXPECTED_API_BASE_URL = "https://wolf.metauniverse-cn.xyz";
const REQUIRED_PAGE_EXTENSIONS = [".js", ".wxml", ".json"];

const results = {
  ok: [],
  warnings: [],
  failures: []
};

function ok(message) {
  results.ok.push(message);
}

function warn(message) {
  results.warnings.push(message);
}

function fail(message) {
  results.failures.push(message);
}

function readJson(relativePath) {
  const absolutePath = path.join(ROOT, relativePath);
  try {
    return JSON.parse(fs.readFileSync(absolutePath, "utf8"));
  } catch (error) {
    fail(`${relativePath} 不是合法 JSON：${error.message}`);
    return null;
  }
}

function pathExists(relativePath) {
  return fs.existsSync(path.join(ROOT, relativePath));
}

function walkFiles(dir, result = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const absolutePath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkFiles(absolutePath, result);
    } else {
      result.push(absolutePath);
    }
  }
  return result;
}

function checkConfig() {
  let config;
  try {
    config = require(path.join(MINIPROGRAM_DIR, "config.js"));
  } catch (error) {
    fail(`miniprogram/config.js 不能加载：${error.message}`);
    return;
  }
  if (config.activeApiEnv !== "production") {
    fail(`activeApiEnv 必须是 production，当前为 ${config.activeApiEnv || "(空)"}`);
  } else {
    ok("activeApiEnv=production。");
  }
  if (config.allowLocalApi) {
    fail("allowLocalApi 必须为 false，避免上传后仍允许本地接口。");
  } else {
    ok("allowLocalApi=false。");
  }
  if (config.apiBaseUrl !== EXPECTED_API_BASE_URL) {
    fail(`apiBaseUrl 必须是 ${EXPECTED_API_BASE_URL}，当前为 ${config.apiBaseUrl || "(空)"}`);
  } else {
    ok("apiBaseUrl 指向正式 HTTPS 域名。");
  }
  if (!/^https:\/\//.test(String(config.apiBaseUrl || ""))) {
    fail("apiBaseUrl 必须使用 https://。");
  }
}

function checkProjectConfig() {
  const projectConfig = readJson("miniprogram/project.config.json");
  if (!projectConfig) {
    return;
  }
  if (projectConfig.appid !== EXPECTED_APPID) {
    fail(`project.config.json appid 应为 ${EXPECTED_APPID}，当前为 ${projectConfig.appid || "(空)"}`);
  } else {
    ok("project.config.json AppID 正确。");
  }
  if (!projectConfig.setting || projectConfig.setting.urlCheck !== true) {
    warn("project.config.json 建议保持 setting.urlCheck=true，避免上传前漏掉合法域名问题。");
  } else {
    ok("urlCheck=true。");
  }
}

function checkAppJson() {
  const appJson = readJson("miniprogram/app.json");
  if (!appJson) {
    return;
  }
  const pages = Array.isArray(appJson.pages) ? appJson.pages : [];
  if (!pages.length) {
    fail("app.json 缺少 pages。");
    return;
  }
  if (pages[0] !== "pages/dashboard/dashboard") {
    fail(`默认首页应为 pages/dashboard/dashboard，当前为 ${pages[0]}`);
  } else {
    ok("默认首页路径正确。");
  }
  for (const pagePath of pages) {
    for (const extension of REQUIRED_PAGE_EXTENSIONS) {
      const relativePath = `miniprogram/${pagePath}${extension}`;
      if (!pathExists(relativePath)) {
        fail(`页面文件缺失：${relativePath}`);
      }
    }
  }
  ok(`页面声明检查完成：${pages.length} 个页面。`);

  const tabList = appJson.tabBar && Array.isArray(appJson.tabBar.list) ? appJson.tabBar.list : [];
  if (!tabList.length) {
    warn("app.json 没有 tabBar 配置。");
    return;
  }
  for (const item of tabList) {
    if (!pages.includes(item.pagePath)) {
      fail(`tabBar pagePath 不在 pages 中：${item.pagePath}`);
    }
    for (const iconKey of ["iconPath", "selectedIconPath"]) {
      const iconPath = item[iconKey];
      if (!iconPath || !pathExists(`miniprogram/${iconPath}`)) {
        fail(`tabBar 图标缺失：${iconPath || `${item.pagePath}.${iconKey}`}`);
      }
    }
  }
  ok(`tabBar 检查完成：${tabList.length} 个入口。`);
}

function checkJavaScriptSyntax() {
  const jsFiles = walkFiles(MINIPROGRAM_DIR).filter((file) => file.endsWith(".js"));
  for (const file of jsFiles) {
    const completed = childProcess.spawnSync(process.execPath, ["--check", file], {
      encoding: "utf8"
    });
    if (completed.status !== 0) {
      const relativePath = path.relative(ROOT, file);
      fail(`${relativePath} JS 语法检查失败：${(completed.stderr || completed.stdout || "").trim()}`);
    }
  }
  ok(`JS 语法检查完成：${jsFiles.length} 个文件。`);
}

function checkLocalAddressRisk() {
  const riskyFiles = walkFiles(MINIPROGRAM_DIR)
    .filter((file) => /\.(js|json|wxml|wxss)$/.test(file))
    .filter((file) => !file.endsWith(path.join("miniprogram", "config.js")))
    .filter((file) => !file.endsWith(path.join("miniprogram", "README.md")))
    .filter((file) => {
      const content = fs.readFileSync(file, "utf8");
      return /https?:\/\/(127\.0\.0\.1|localhost|0\.0\.0\.0)(:\d+)?/i.test(content);
    });
  if (riskyFiles.length) {
    for (const file of riskyFiles) {
      fail(`发现本地接口地址风险：${path.relative(ROOT, file)}`);
    }
  } else {
    ok("未在发布文件中发现本地接口地址。");
  }
}

function checkPredictionShareCard() {
  const sourcePath = path.join(MINIPROGRAM_DIR, "pages", "prediction-share-card", "prediction-share-card.js");
  const templatePath = path.join(MINIPROGRAM_DIR, "pages", "prediction-share-card", "prediction-share-card.wxml");
  const source = fs.readFileSync(sourcePath, "utf8");
  const template = fs.readFileSync(templatePath, "utf8");
  const required = [
    "const CARD_HEIGHT = 1900;",
    "player.expectedTotal",
    "基于历史数据进行可复现模拟",
    "结果仅供赛前数据参考",
    "一颗小草赛事数据中心"
  ];
  for (const text of required) {
    if (!source.includes(text)) {
      fail(`预测分享图缺少关键内容：${text}`);
    }
  }
  for (const text of ["expectedWins", "manualOverrideApplied", "player.markets", "4神4民4狼"]) {
    if (source.includes(text)) {
      fail(`预测分享图仍包含已移除内容：${text}`);
    }
  }
  if (!template.includes("自动汇总12名选手的当天预测总分")) {
    fail("预测分享页介绍未改为仅展示当天预测总分。");
  }
  const forbiddenTerms = ["盘口", "赔率", "下注", "投注", "走水", "通杀"];
  for (const file of walkFiles(MINIPROGRAM_DIR).filter((item) => /\.(js|json|wxml|wxss)$/.test(item))) {
    const content = fs.readFileSync(file, "utf8");
    for (const term of forbiddenTerms) {
      if (content.includes(term)) {
        fail(`小程序页面包含禁用预测用语：${path.relative(ROOT, file)}（${term}）`);
      }
    }
  }
  ok("预测分享图仅展示12人预测总分，且页面用语检查通过。");
}

function printReport() {
  console.log("小程序发布前自检");
  for (const message of results.ok) {
    console.log(`[OK] ${message}`);
  }
  for (const message of results.warnings) {
    console.log(`[WARN] ${message}`);
  }
  for (const message of results.failures) {
    console.log(`[FAIL] ${message}`);
  }
}

function main() {
  checkConfig();
  checkProjectConfig();
  checkAppJson();
  checkJavaScriptSyntax();
  checkLocalAddressRisk();
  checkPredictionShareCard();
  printReport();
  if (results.failures.length) {
    console.error("\n小程序发布前自检未通过，请先修正失败项。");
    process.exit(1);
  }
  console.log("\n小程序发布前自检通过。");
}

main();
