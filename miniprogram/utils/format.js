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

module.exports = {
  compactText,
  metricValue,
  take
};
