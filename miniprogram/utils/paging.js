const DEFAULT_PAGE_SIZE = 30;

function createPagedState(items, pageSize = DEFAULT_PAGE_SIZE) {
  const list = Array.isArray(items) ? items : [];
  const size = Number(pageSize) > 0 ? Number(pageSize) : DEFAULT_PAGE_SIZE;
  return {
    allItems: list,
    visibleItems: list.slice(0, size),
    pageSize: size,
    visibleCount: Math.min(size, list.length),
    totalCount: list.length,
    hasMore: list.length > size
  };
}

function nextPagedState(state) {
  const list = Array.isArray(state && state.allItems) ? state.allItems : [];
  const size = Number(state && state.pageSize) > 0 ? Number(state.pageSize) : DEFAULT_PAGE_SIZE;
  const current = Number(state && state.visibleCount) || 0;
  const nextCount = Math.min(current + size, list.length);
  return {
    allItems: list,
    visibleItems: list.slice(0, nextCount),
    pageSize: size,
    visibleCount: nextCount,
    totalCount: list.length,
    hasMore: nextCount < list.length
  };
}

module.exports = {
  DEFAULT_PAGE_SIZE,
  createPagedState,
  nextPagedState
};
