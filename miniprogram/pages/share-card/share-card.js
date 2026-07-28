const { request, assetUrl } = require("../../utils/api");
const { getRequiredScope, scopeParams } = require("../../utils/scope");
const { apiBaseUrl } = require("../../config");

const VERTICAL_CARD = { width: 694, height: 1041 };
const LANDSCAPE_CARD = { width: 1041, height: 694 };

function loadImage(canvas, source) {
  return new Promise((resolve, reject) => {
    if (!source) {
      reject(new Error("图片地址为空"));
      return;
    }
    const image = canvas.createImage();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("图片加载失败"));
    image.src = source;
  });
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

function drawCircularAvatar(ctx, image, centerX, centerY, radius) {
  const imageWidth = Number(image.width || image.naturalWidth || 0);
  const imageHeight = Number(image.height || image.naturalHeight || 0);
  ctx.save();
  ctx.beginPath();
  ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
  ctx.clip();
  if (imageWidth > 0 && imageHeight > 0) {
    const sourceSize = Math.min(imageWidth, imageHeight);
    const sourceX = (imageWidth - sourceSize) / 2;
    const sourceY = (imageHeight - sourceSize) / 2;
    ctx.drawImage(
      image,
      sourceX,
      sourceY,
      sourceSize,
      sourceSize,
      centerX - radius,
      centerY - radius,
      radius * 2,
      radius * 2
    );
  } else {
    ctx.drawImage(image, centerX - radius, centerY - radius, radius * 2, radius * 2);
  }
  ctx.restore();
}

function drawAvatarPlaceholder(ctx, player, centerX, centerY, radius) {
  const playerName = String(player.name || player.display_name || "").trim();
  ctx.save();
  ctx.beginPath();
  ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
  ctx.fillStyle = "#211b10";
  ctx.fill();
  drawText(ctx, playerName.slice(0, 1) || "狼", centerX, centerY + radius * 0.28, {
    size: Math.round(radius * 0.85),
    color: "#d4af37",
    weight: 700,
    align: "center"
  });
  ctx.restore();
}

function drawAvatarFrame(ctx, centerX, centerY, radius) {
  ctx.beginPath();
  ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
  ctx.strokeStyle = "#d4af37";
  ctx.lineWidth = 3;
  ctx.stroke();
}

function drawText(ctx, text, x, y, options = {}) {
  ctx.fillStyle = options.color || "#f8f0d8";
  ctx.font = `${options.weight || 500} ${options.size || 28}px sans-serif`;
  ctx.textAlign = options.align || "left";
  ctx.fillText(String(text || "--"), x, y);
}

function drawStarBadge(ctx, x, y, compact = false) {
  const width = compact ? 118 : 142;
  const height = compact ? 32 : 38;
  const radius = height / 2;
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + width - radius, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
  ctx.lineTo(x + width, y + height - radius);
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  ctx.lineTo(x + radius, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
  ctx.fillStyle = "#f3bd38";
  ctx.fill();
  ctx.strokeStyle = "#ffe08a";
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(x + 16, y + height / 2, compact ? 4 : 5, 0, Math.PI * 2);
  ctx.fillStyle = "#3b2800";
  ctx.fill();
  drawText(ctx, "明星选手", x + 28, y + (compact ? 23 : 27), {
    size: compact ? 18 : 21,
    color: "#2b1b00",
    weight: 700
  });
}

Page({
  data: {
    loading: true,
    error: "",
    mode: "vertical",
    achievements: [],
    selectedAchievementCodes: []
  },

  onLoad(options) {
    this.playerId = decodeURIComponent(options.player_id || "");
    this.renderCard();
  },

  async renderCard() {
    try {
      const scope = getRequiredScope();
      if (!this.playerId || !scope) {
        throw new Error("请先进入赛事后再生成战绩卡。" );
      }
      const payload = await request(`/api/players/${encodeURIComponent(this.playerId)}`, scopeParams(scope));
      this.payload = payload;
      this.scope = scope;
      const achievements = (payload.achievements || []).slice(0, 6).map((item) => ({
        code: item.code,
        title: item.title,
        meta: item.meta || "",
        selected: this.data.selectedAchievementCodes.indexOf(item.code) >= 0
      }));
      const selectedAchievementCodes = this.data.selectedAchievementCodes.length
        ? this.data.selectedAchievementCodes.filter((code) => achievements.some((item) => item.code === code))
        : achievements.slice(0, 2).map((item) => item.code);
      this.setData({ achievements, selectedAchievementCodes }, () => this.initCanvas(payload, scope));
    } catch (error) {
      this.setData({ loading: false, error: error.message || "生成战绩卡失败。" });
    }
  },

  initCanvas(payload, scope) {
    const dimensions = this.data.mode === "landscape" ? LANDSCAPE_CARD : VERTICAL_CARD;
    this.setData({ loading: true, error: "" });
      const query = wx.createSelectorQuery();
      query.select("#shareCanvas").fields({ node: true, size: true }).exec(async (result) => {
        try {
          const target = result[0];
          if (!target || !target.node) {
            this.setData({ loading: false, error: "战绩卡画布初始化失败。" });
            return;
          }
          const canvas = target.node;
          const ratio = wx.getSystemInfoSync().pixelRatio || 1;
          canvas.width = dimensions.width * ratio;
          canvas.height = dimensions.height * ratio;
          const ctx = canvas.getContext("2d");
          ctx.scale(ratio, ratio);
          await this.drawCard(ctx, canvas, payload, scope);
          this.canvas = canvas;
          this.setData({ loading: false, error: "" });
        } catch (error) {
          this.setData({ loading: false, error: error.message || "绘制战绩卡失败。" });
        }
      });
  },

  async drawCard(ctx, canvas, payload, scope) {
    const player = payload.player || {};
    const metrics = payload.metrics || [];
    const points = (metrics.find((item) => item.label && item.label.indexOf("积分") >= 0) || {}).value || "--";
    const winRate = (payload.insights || {}).overall_win_rate || "--";
    const mvp = (payload.insights || {}).mvp_count !== undefined
      ? String((payload.insights || {}).mvp_count)
      : ((metrics.find((item) => item.label && item.label.toUpperCase().indexOf("MVP") >= 0) || {}).value || "0");
    if (this.data.mode === "landscape") {
      await this.drawLandscapeCard(ctx, canvas, { player, points, winRate, mvp }, scope);
      return;
    }
    const avatar = await this.loadPlayerAvatar(canvas, player);
    const { width: CARD_WIDTH, height: CARD_HEIGHT } = VERTICAL_CARD;
    ctx.fillStyle = "#0b0b0c";
    ctx.fillRect(0, 0, CARD_WIDTH, CARD_HEIGHT);
    ctx.strokeStyle = "#d4af37";
    ctx.lineWidth = 2;
    ctx.strokeRect(20, 20, CARD_WIDTH - 40, CARD_HEIGHT - 40);
    ctx.globalAlpha = 0.16;
    for (let offset = 0; offset < CARD_WIDTH; offset += 34) {
      ctx.beginPath(); ctx.moveTo(offset, 20); ctx.lineTo(CARD_WIDTH - 20, CARD_HEIGHT - offset); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    if (avatar) drawCircularAvatar(ctx, avatar, 120, 132, 74);
    else drawAvatarPlaceholder(ctx, player, 120, 132, 74);
    drawAvatarFrame(ctx, 120, 132, 74);
    drawText(ctx, player.name || player.display_name || this.playerId, 220, 115, { size: 44, weight: 700 });
    if (player.is_star_player) drawStarBadge(ctx, 220, 135);
    drawText(ctx, player.team_name || "未绑定战队", 220, player.is_star_player ? 205 : 162, { size: 25, color: "#d4af37" });
    drawText(ctx, "赛季排名", 66, 306, { size: 28, color: "#d4af37", weight: 700 });
    drawText(ctx, `#${player.rank || "--"}`, 66, 438, { size: 118, color: "#d4af37", weight: 700 });
    const cards = [["总积分", points], ["胜率", winRate], ["MVP", mvp]];
    cards.forEach((item, index) => {
      const x = 46 + index * 216;
      ctx.strokeStyle = "#d4af37"; ctx.strokeRect(x, 530, 188, 218);
      drawText(ctx, item[0], x + 94, 590, { size: 27, color: "#d4af37", weight: 700, align: "center" });
      drawText(ctx, item[1], x + 94, 685, { size: 48, weight: 700, align: "center" });
    });
    this.drawAchievements(ctx, 50, 792, 380);
    try {
      const qrPath = await downloadImage(
        `${String(apiBaseUrl).replace(/\/+$/, "")}/api/miniprogram/share-code?player_id=${encodeURIComponent(this.playerId)}`,
        "小程序码"
      );
      const qr = await loadImage(canvas, qrPath);
      ctx.fillStyle = "#ffffff"; ctx.fillRect(470, 804, 172, 172);
      ctx.drawImage(qr, 482, 816, 148, 148);
    } catch (error) {
      ctx.strokeStyle = "#d4af37"; ctx.strokeRect(470, 804, 172, 172);
    }
    drawText(ctx, scope.competition, 50, 920, { size: 23, color: "#b8a77a" });
    drawText(ctx, scope.season || "当前赛季", 50, 956, { size: 23, color: "#b8a77a" });
  },

  async loadPlayerAvatar(canvas, player) {
    const photoUrl = assetUrl(player.photo);
    if (!photoUrl) {
      return null;
    }
    try {
      const photoPath = /^https?:\/\//i.test(photoUrl)
        ? await downloadImage(photoUrl, "选手头像")
        : photoUrl;
      return await loadImage(canvas, photoPath);
    } catch (error) {
      return null;
    }
  },

  drawAchievements(ctx, x, y, maxWidth) {
    const selected = (this.data.achievements || []).filter((item) => this.data.selectedAchievementCodes.indexOf(item.code) >= 0);
    if (!selected.length) {
      return;
    }
    drawText(ctx, "成就", x, y, { size: 20, color: "#d4af37", weight: 700 });
    selected.slice(0, 2).forEach((item, index) => {
      const label = `${item.title}${item.meta ? ` · ${item.meta}` : ""}`;
      drawText(ctx, label.slice(0, Math.floor(maxWidth / 18)), x, y + 32 + index * 28, { size: 18, color: "#f8f0d8" });
    });
  },

  async drawLandscapeCard(ctx, canvas, values, scope) {
    const avatar = await this.loadPlayerAvatar(canvas, values.player);
    const { width, height } = LANDSCAPE_CARD;
    ctx.fillStyle = "#0b0b0c";
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = "#d4af37";
    ctx.lineWidth = 2;
    ctx.strokeRect(20, 20, width - 40, height - 40);
    ctx.globalAlpha = 0.14;
    for (let offset = -height; offset < width; offset += 42) {
      ctx.beginPath(); ctx.moveTo(offset, 20); ctx.lineTo(offset + height, height - 20); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    if (avatar) drawCircularAvatar(ctx, avatar, 126, 135, 76);
    else drawAvatarPlaceholder(ctx, values.player, 126, 135, 76);
    drawAvatarFrame(ctx, 126, 135, 76);
    drawText(ctx, values.player.name || values.player.display_name || this.playerId, 235, 116, { size: 46, weight: 700 });
    if (values.player.is_star_player) drawStarBadge(ctx, 235, 134, true);
    drawText(ctx, values.player.team_name || "未绑定战队", 235, values.player.is_star_player ? 202 : 162, { size: 25, color: "#d4af37" });
    drawText(ctx, "赛季排名", 55, 315, { size: 26, color: "#d4af37", weight: 700 });
    drawText(ctx, `#${values.player.rank || "--"}`, 55, 446, { size: 122, color: "#d4af37", weight: 700 });
    [["总积分", values.points], ["胜率", values.winRate], ["MVP", values.mvp]].forEach((item, index) => {
      const x = 370 + index * 142;
      ctx.strokeStyle = "#d4af37"; ctx.strokeRect(x, 262, 124, 154);
      drawText(ctx, item[0], x + 62, 311, { size: 20, color: "#d4af37", weight: 700, align: "center" });
      drawText(ctx, item[1], x + 62, 374, { size: 34, weight: 700, align: "center" });
    });
    this.drawAchievements(ctx, 55, 523, 560);
    try {
      const qrPath = await downloadImage(
        `${String(apiBaseUrl).replace(/\/+$/, "")}/api/miniprogram/share-code?player_id=${encodeURIComponent(this.playerId)}`,
        "小程序码"
      );
      const qr = await loadImage(canvas, qrPath);
      ctx.fillStyle = "#ffffff"; ctx.fillRect(820, 470, 164, 164);
      ctx.drawImage(qr, 832, 482, 140, 140);
    } catch (error) {
      ctx.strokeStyle = "#d4af37"; ctx.strokeRect(820, 470, 164, 164);
    }
    drawText(ctx, scope.competition, 55, 620, { size: 20, color: "#b8a77a" });
    drawText(ctx, scope.season || "当前赛季", 55, 650, { size: 20, color: "#b8a77a" });
  },

  setMode(event) {
    const mode = event.currentTarget.dataset.mode;
    if (!mode || mode === this.data.mode) return;
    this.setData({ mode }, () => this.initCanvas(this.payload, this.scope));
  },

  toggleAchievement(event) {
    const code = event.currentTarget.dataset.code;
    const selected = this.data.selectedAchievementCodes.slice();
    const index = selected.indexOf(code);
    if (index >= 0) selected.splice(index, 1);
    else if (selected.length < 2) selected.push(code);
    else {
      wx.showToast({ title: "最多选择 2 个成就", icon: "none" });
      return;
    }
    const achievements = this.data.achievements.map((item) => ({ ...item, selected: selected.indexOf(item.code) >= 0 }));
    this.setData({ achievements, selectedAchievementCodes: selected }, () => this.initCanvas(this.payload, this.scope));
  },

  exportCard(callback) {
    if (!this.canvas) { callback(new Error("战绩卡仍在生成中。")); return; }
    wx.canvasToTempFilePath({
      canvas: this.canvas,
      fileType: "png",
      quality: 1,
      success: (result) => callback(null, result.tempFilePath),
      fail: () => callback(new Error("导出战绩卡失败。"))
    });
  },

  previewCard() {
    this.exportCard((error, path) => {
      if (error) { wx.showToast({ title: error.message, icon: "none" }); return; }
      wx.previewImage({ urls: [path] });
    });
  },

  saveCard() {
    this.exportCard((error, path) => {
      if (error) { wx.showToast({ title: error.message, icon: "none" }); return; }
      wx.saveImageToPhotosAlbum({
        filePath: path,
        success: () => wx.showToast({ title: "已保存到相册", icon: "success" }),
        fail: () => wx.showToast({ title: "请允许保存图片权限后重试", icon: "none" })
      });
    });
  }
});
