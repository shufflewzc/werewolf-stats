const { request } = require("../../utils/api");
const { getRequiredScope, scopeParams } = require("../../utils/scope");
const { apiBaseUrl } = require("../../config");

const CARD_WIDTH = 694;
const CARD_HEIGHT = 1041;

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

function download(url) {
  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url,
      success(response) {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.tempFilePath);
          return;
        }
        reject(new Error("小程序码下载失败"));
      },
      fail() {
        reject(new Error("小程序码下载失败"));
      }
    });
  });
}

function drawText(ctx, text, x, y, options = {}) {
  ctx.fillStyle = options.color || "#f8f0d8";
  ctx.font = `${options.weight || 500} ${options.size || 28}px sans-serif`;
  ctx.textAlign = options.align || "left";
  ctx.fillText(String(text || "--"), x, y);
}

Page({
  data: { loading: true, error: "" },

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
          canvas.width = CARD_WIDTH * ratio;
          canvas.height = CARD_HEIGHT * ratio;
          const ctx = canvas.getContext("2d");
          ctx.scale(ratio, ratio);
          await this.drawCard(ctx, canvas, payload, scope);
          this.canvas = canvas;
          this.setData({ loading: false, error: "" });
        } catch (error) {
          this.setData({ loading: false, error: error.message || "绘制战绩卡失败。" });
        }
      });
    } catch (error) {
      this.setData({ loading: false, error: error.message || "生成战绩卡失败。" });
    }
  },

  async drawCard(ctx, canvas, payload, scope) {
    const player = payload.player || {};
    const metrics = payload.metrics || [];
    const points = (metrics.find((item) => item.label && item.label.indexOf("积分") >= 0) || {}).value || "--";
    const winRate = (payload.insights || {}).overall_win_rate || "--";
    const mvp = (metrics.find((item) => item.label && item.label.toUpperCase().indexOf("MVP") >= 0) || {}).value || "--";
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
    ctx.beginPath(); ctx.arc(120, 132, 74, 0, Math.PI * 2); ctx.stroke();
    drawText(ctx, player.name || player.display_name || this.playerId, 220, 115, { size: 44, weight: 700 });
    drawText(ctx, player.team_name || "未绑定战队", 220, 162, { size: 25, color: "#d4af37" });
    drawText(ctx, "赛季排名", 66, 306, { size: 28, color: "#d4af37", weight: 700 });
    drawText(ctx, `#${player.rank || "--"}`, 66, 438, { size: 118, color: "#d4af37", weight: 700 });
    const cards = [["总积分", points], ["胜率", winRate], ["MVP", mvp]];
    cards.forEach((item, index) => {
      const x = 46 + index * 216;
      ctx.strokeStyle = "#d4af37"; ctx.strokeRect(x, 530, 188, 218);
      drawText(ctx, item[0], x + 94, 590, { size: 27, color: "#d4af37", weight: 700, align: "center" });
      drawText(ctx, item[1], x + 94, 685, { size: 48, weight: 700, align: "center" });
    });
    try {
      const qrPath = await download(`${String(apiBaseUrl).replace(/\/+$/, "")}/api/miniprogram/share-code?player_id=${encodeURIComponent(this.playerId)}`);
      const qr = await loadImage(canvas, qrPath);
      ctx.fillStyle = "#ffffff"; ctx.fillRect(470, 804, 172, 172);
      ctx.drawImage(qr, 482, 816, 148, 148);
    } catch (error) {
      ctx.strokeStyle = "#d4af37"; ctx.strokeRect(470, 804, 172, 172);
    }
    drawText(ctx, scope.competition, 50, 920, { size: 23, color: "#b8a77a" });
    drawText(ctx, scope.season || "当前赛季", 50, 956, { size: 23, color: "#b8a77a" });
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
