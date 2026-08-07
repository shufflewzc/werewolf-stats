function metricValue(metrics, label, fallback = "--") {
  const found = Array.isArray(metrics) ? metrics.find((item) => item.label === label) : null;
  return found ? found.value : fallback;
}

function take(items, count) {
  return Array.isArray(items) ? items.slice(0, count) : [];
}

function compactText(parts, separator = " · ") {
  return parts.filter(Boolean).join(separator);
}

function stageLabel(item, fallback = "赛段") {
  const source = item || {};
  const values = [source.stage_label, source.stage, fallback];
  for (let index = 0; index < values.length; index += 1) {
    const value = String(values[index] || "").trim();
    if (value) {
      return value;
    }
  }
  return "";
}

module.exports = {
  compactText,
  metricValue,
  stageLabel,
  take
};
