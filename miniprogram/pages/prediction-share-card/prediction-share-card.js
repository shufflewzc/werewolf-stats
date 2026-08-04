const { request } = require("../../utils/api");
const { appendScopeToPath, applyScopeFromOptions, getRequiredScope, scopeParams } = require("../../utils/scope");
const { apiBaseUrl } = require("../../config");

const CARD_WIDTH = 750;
const CARD_HEIGHT = 3000;
const MAX_CANVAS_EDGE = 4096;
const MARKET_KEYS = ["lt_0", "lt_5", "lt_10", "gt_10", "gt_15", "gt_18"];
const MARKET_LABELS = {
  lt_0: "小0",
  lt_5: "小5",
  lt_10: "小10",
  gt_10: "大10",
  gt_15: "大15",
  gt_18: "大18"
};

function safeDecode(value) {
  try {
    return decodeURIComponent(value || "");
  } catch (error) {
    return String(value || "");
  }
}

function buildQuery(params) {
  return Object.keys(params || {})
    .filter((key) => params[key] !== undefined && params[key] !== null && params[key] !== "")
    .map((key) => `${encodeURIComponent(key)}=${encodeURIComponent(params[key])}`)
    .join("&");
}

function downloadImage(url, label = "图片") {
  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url,
      success(response) {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.tempFilePath);
          return;
        }
        reject(new Error(`${label}下载失败`));
      },
      fail() {
        reject(new Error(`${label}下载失败`));
      }
    });
  });
}

function loadImage(canvas, source) {
  return new Promise((resolve, reject) => {
    const image = canvas.createImage();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("小程序码图片加载失败"));
    image.src = source;
  });
}

function textFont(options = {}) {
  return `${options.weight || 500} ${options.size || 24}px sans-serif`;
}

function fittedText(ctx, value, maxWidth) {
  const text = String(value || "--");
  if (!maxWidth || ctx.measureText(text).width <= maxWidth) {
    return text;
  }
  let result = text;
  while (result.length > 1 && ctx.measureText(`${result}…`).width > maxWidth) {
    result = result.slice(0, -1);
  }
  return `${result}…`;
}

function drawText(ctx, value, x, y, options = {}) {
  ctx.save();
  ctx.fillStyle = options.color || "#f8f0d8";
  ctx.font = textFont(options);
  ctx.textAlign = options.align || "left";
  ctx.textBaseline = options.baseline || "alphabetic";
  const text = fittedText(ctx, value, options.maxWidth);
  ctx.fillText(text, x, y);
  ctx.restore();
}

function roundedRect(ctx, x, y, width, height, radius, options = {}) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + width - r, y);
  ctx.arcTo(x + width, y, x + width, y + r, r);
  ctx.lineTo(x + width, y + height - r);
  ctx.arcTo(x + width, y + height, x + width - r, y + height, r);
  ctx.lineTo(x + r, y + height);
  ctx.arcTo(x, y + height, x, y + height - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
  if (options.fill) {
    ctx.fillStyle = options.fill;
    ctx.fill();
  }
  if (options.stroke) {
    ctx.strokeStyle = options.stroke;
    ctx.lineWidth = options.lineWidth || 1;
    ctx.stroke();
  }
  ctx.restore();
}

function percentageDisplay(market) {
  if (market && market.display) {
    return String(market.display);
  }
  return `${(Number((market && market.probability) || 0) * 100).toFixed(1)}%`;
}

function normalizePredictions(payload, playedOn) {
  const selectedDay = payload.selected_day || {};
  if (selectedDay.played_on !== playedOn) {
    throw new Error("服务器未返回所选比赛日的预测，请返回后重新选择日期。");
  }
  const predictions = Array.isArray(payload.predictions) ? payload.predictions : [];
  if (predictions.length !== 12) {
    throw new Error("当天预测名单必须完整为12人后才能生成分享图。");
  }
  const ids = new Set(predictions.map((item) => String(item.player_id || "").trim()));
  if (ids.size !== 12 || ids.has("")) {
    throw new Error("当天预测名单存在重复或无效选手，暂时无法生成分享图。");
  }
  return predictions.map((item, index) => {
    const marketLookup = {};
    (item.market_probabilities || []).forEach((market) => {
      marketLookup[market.key] = market;
    });
    const markets = MARKET_KEYS.map((key) => marketLookup[key]);
    if (markets.some((market) => !market)) {
      throw new Error(`${item.player_name || "选手"}缺少完整的六项盘口概率。`);
    }
    return {
      rank: Number(item.rank || index + 1),
      playerId: String(item.player_id || ""),
      playerName: String(item.player_name || item.player_id || "未知选手"),
      teamName: String(item.team_name || "未绑定战队"),
      expectedTotal: Number(item.expected_total || item.expected_points || 0).toFixed(2),
      expectedWins: Number(item.expected_wins || 0).toFixed(2),
      manualOverrideApplied: Boolean(item.manual_override_applied),
      markets: markets.map((market, marketIndex) => ({
        key: MARKET_KEYS[marketIndex],
        label: market.label || MARKET_LABELS[MARKET_KEYS[marketIndex]],
        display: percentageDisplay(market)
      }))
    };
  }).sort((left, right) => left.rank - right.rank);
}

Page({
  data: {
    loading: true,
    error: "",
    cardReady: false
  },

  onLoad(options) {
    applyScopeFromOptions(options);
    this.playedOn = safeDecode(options.played_on);
    this.renderCard();
  },

  onShareAppMessage() {
    const scope = this.scope || getRequiredScope();
    return {
      title: `${scope && scope.competition ? scope.competition : "狼人杀赛事"} · ${this.playedOn || "当天"}预测`,
      path: appendScopeToPath(
        `/pages/predictions/predictions?played_on=${encodeURIComponent(this.playedOn || "")}`,
        scope
      )
    };
  },

  async renderCard(options = {}) {
    this.canvas = null;
    this.setData({ loading: true, error: "", cardReady: false });
    try {
      const scope = getRequiredScope();
      if (!scope || !scope.competition || !scope.season || !this.playedOn) {
        throw new Error("缺少赛事、赛季或比赛日期，请从当天预测页重新进入。");
      }
      const payload = await request("/api/predictions", {
        ...scopeParams(scope),
        played_on: this.playedOn,
        limit: 30,
        offset: 0
      }, { forceRefresh: Boolean(options.forceRefresh) });
      const predictions = normalizePredictions(payload, this.playedOn);
      const qrUrl = `${String(apiBaseUrl).replace(/\/+$/, "")}/api/miniprogram/share-code?${buildQuery({
        share_type: "prediction_day",
        competition: scope.competition,
        season: scope.season,
        played_on: this.playedOn
      })}`;
      const qrPath = await downloadImage(qrUrl, "小程序码");
      this.scope = scope;
      this.payload = payload;
      this.predictions = predictions;
      await this.initCanvas(payload, predictions, scope, qrPath);
      this.setData({ loading: false, error: "", cardReady: true });
    } catch (error) {
      this.canvas = null;
      this.setData({
        loading: false,
        cardReady: false,
        error: error.message || "预测分享图生成失败，请稍后重试。"
      });
    }
  },

  initCanvas(payload, predictions, scope, qrPath) {
    return new Promise((resolve, reject) => {
      const query = wx.createSelectorQuery();
      query.select("#predictionShareCanvas").fields({ node: true, size: true }).exec(async (result) => {
        try {
          const target = result[0];
          if (!target || !target.node) {
            throw new Error("预测分享图画布初始化失败。");
          }
          const canvas = target.node;
          const pixelRatio = Number(wx.getSystemInfoSync().pixelRatio || 1);
          const renderScale = Math.max(1, Math.min(2, pixelRatio, MAX_CANVAS_EDGE / CARD_HEIGHT));
          canvas.width = Math.round(CARD_WIDTH * renderScale);
          canvas.height = Math.round(CARD_HEIGHT * renderScale);
          const ctx = canvas.getContext("2d");
          ctx.scale(renderScale, renderScale);
          const qrImage = await loadImage(canvas, qrPath);
          this.drawCard(ctx, payload, predictions, scope, qrImage);
          this.canvas = canvas;
          resolve();
        } catch (error) {
          reject(error);
        }
      });
    });
  },

  drawCard(ctx, payload, predictions, scope, qrImage) {
    const gold = "#d7ad45";
    const mutedGold = "#b9a26f";
    const text = "#f8f0d8";
    const muted = "#b7beca";
    const background = ctx.createLinearGradient(0, 0, CARD_WIDTH, CARD_HEIGHT);
    background.addColorStop(0, "#08090c");
    background.addColorStop(0.55, "#10131a");
    background.addColorStop(1, "#07080a");
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, CARD_WIDTH, CARD_HEIGHT);

    ctx.save();
    ctx.globalAlpha = 0.07;
    ctx.strokeStyle = gold;
    ctx.lineWidth = 1;
    for (let offset = -CARD_HEIGHT; offset < CARD_WIDTH; offset += 74) {
      ctx.beginPath();
      ctx.moveTo(offset, 20);
      ctx.lineTo(offset + CARD_HEIGHT, CARD_HEIGHT - 20);
      ctx.stroke();
    }
    ctx.restore();
    roundedRect(ctx, 18, 18, CARD_WIDTH - 36, CARD_HEIGHT - 36, 18, { stroke: gold, lineWidth: 2 });

    drawText(ctx, "JCDS · PREDICTION REPORT", 42, 62, { size: 20, weight: 700, color: gold });
    drawText(ctx, "当天三局胜率预测", 42, 119, { size: 46, weight: 800, color: text });
    drawText(ctx, scope.competition, 42, 165, { size: 29, weight: 700, color: gold, maxWidth: 666 });
    drawText(ctx, `${scope.season} · ${this.playedOn}`, 42, 205, { size: 23, color: muted, maxWidth: 666 });
    const simulations = Number((payload.model_metadata || {}).simulations || 10000).toLocaleString("zh-CN");
    drawText(ctx, `12名选手 · ${simulations}次可复现模拟 · 按预计总分排序`, 42, 238, { size: 19, color: mutedGold });

    predictions.forEach((player, index) => {
      const y = 255 + index * 195;
      roundedRect(ctx, 34, y, 682, 181, 14, {
        fill: index % 2 ? "rgba(24, 28, 37, 0.96)" : "rgba(17, 20, 27, 0.96)",
        stroke: index < 3 ? "#8f742f" : "#323845",
        lineWidth: index < 3 ? 1.5 : 1
      });
      roundedRect(ctx, 47, y + 17, 29, 29, 14, { fill: index < 3 ? gold : "#343a46" });
      drawText(ctx, player.rank, 61.5, y + 38, {
        size: 17,
        weight: 800,
        color: index < 3 ? "#17130a" : text,
        align: "center"
      });
      drawText(ctx, player.playerName, 88, y + 41, { size: 27, weight: 800, color: text, maxWidth: 188 });
      drawText(ctx, player.teamName, 292, y + 40, { size: 20, color: muted, maxWidth: 168 });
      drawText(
        ctx,
        `总分 ${player.expectedTotal}${player.manualOverrideApplied ? "*" : ""} · ${player.expectedWins}胜`,
        694,
        y + 40,
        { size: 22, weight: 700, color: gold, align: "right", maxWidth: 218 }
      );

      player.markets.forEach((market, marketIndex) => {
        const column = marketIndex % 3;
        const row = Math.floor(marketIndex / 3);
        const boxX = 47 + column * 221;
        const boxY = y + 67 + row * 49;
        roundedRect(ctx, boxX, boxY, 207, 39, 8, { fill: "#161b23", stroke: "#2d3440" });
        drawText(ctx, market.label, boxX + 12, boxY + 27, { size: 19, weight: 700, color: mutedGold });
        drawText(ctx, market.display, boxX + 195, boxY + 28, { size: 22, weight: 800, color: text, align: "right" });
      });
    });

    ctx.strokeStyle = "#6f5a28";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(42, 2613);
    ctx.lineTo(708, 2613);
    ctx.stroke();
    drawText(ctx, "预测说明", 44, 2660, { size: 23, weight: 800, color: gold });
    drawText(ctx, "系统每局随机分配4神、4民、4狼", 44, 2703, { size: 22, color: text });
    drawText(ctx, "等于盘口不计命中", 44, 2742, { size: 22, color: text });
    drawText(ctx, "预测概率不等于赔率", 44, 2781, { size: 22, color: text });
    if (predictions.some((player) => player.manualOverrideApplied)) {
      drawText(ctx, "* 表示管理员人工修正预计总分", 44, 2820, { size: 19, color: mutedGold });
    }
    const modelVersion = String((payload.model_metadata || {}).version || "prediction_model");
    drawText(ctx, `模型 ${modelVersion}`, 44, 2870, { size: 18, color: muted, maxWidth: 420 });
    drawText(ctx, "更多三局胜率与胜场分布，请扫码查看", 44, 2910, { size: 18, color: muted, maxWidth: 430 });

    roundedRect(ctx, 522, 2673, 184, 184, 12, { fill: "#ffffff" });
    ctx.drawImage(qrImage, 534, 2685, 160, 160);
    drawText(ctx, "扫码查看当天预测", 614, 2894, { size: 19, weight: 700, color: gold, align: "center" });
    drawText(ctx, "京城大师赛数据中心", 375, 2960, { size: 20, weight: 700, color: mutedGold, align: "center" });
  },

  regenerateCard() {
    this.renderCard({ forceRefresh: true });
  },

  exportCard(callback) {
    if (!this.canvas || !this.data.cardReady) {
      callback(new Error("预测分享图仍在生成中。"));
      return;
    }
    wx.canvasToTempFilePath({
      canvas: this.canvas,
      fileType: "png",
      quality: 1,
      success: (result) => callback(null, result.tempFilePath),
      fail: () => callback(new Error("预测分享图导出失败，请重新生成。"))
    });
  },

  previewCard() {
    this.exportCard((error, path) => {
      if (error) {
        wx.showToast({ title: error.message, icon: "none" });
        return;
      }
      wx.previewImage({ urls: [path] });
    });
  },

  saveCard() {
    this.exportCard((error, path) => {
      if (error) {
        wx.showToast({ title: error.message, icon: "none" });
        return;
      }
      wx.saveImageToPhotosAlbum({
        filePath: path,
        success: () => wx.showToast({ title: "已保存到相册", icon: "success" }),
        fail: () => wx.showToast({ title: "请允许相册权限后重试", icon: "none" })
      });
    });
  }
});
