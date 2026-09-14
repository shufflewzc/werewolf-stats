const { request, assetUrl } = require('../../utils/api');
const { getRequiredScope, scopeParams, sameScope, goCompetitions, needsCompetitionState, appendScopeToPath } = require('../../utils/scope');

function decorate(report) {
  return { ...report, sections: (report.sections || []).map(section => ({
    ...section, matches: (section.matches || []).map(match => ({
      ...match, photoUrl: assetUrl(match.mvp && match.mvp.photo),
      guildLogoUrl: assetUrl(match.mvp && match.mvp.guild_logo)
    }))
  })) };
}

Page({
  data: { loading: true, loadingMore: false, error: '', needsCompetition: false,
    selectedScope: null, reports: [], hasReports: false, hasMore: false, total: 0 },
  onShow() { return this.loadData(); },
  onPullDownRefresh() {
    return this.loadData({ forceRefresh: true }).finally(() => wx.stopPullDownRefresh());
  },
  onReachBottom() { return this.loadMore(); },
  goCompetitions() { goCompetitions(); },
  retry() { return this.loadData({ forceRefresh: true }); },
  loadMore() {
    if (this.data.loading || this.data.loadingMore || !this.data.hasMore) return;
    return this.loadData({ append: true });
  },
  async loadData(options = {}) {
    const scope = getRequiredScope();
    const append = Boolean(options.append);
    if (append && (!sameScope(scope, this.data.selectedScope) || this.data.loadingMore)) return;
    const requestId = (this._requestId || 0) + 1;
    this._requestId = requestId;
    if (!scope) {
      this.setData(needsCompetitionState({ reports: [], hasReports: false, hasMore: false, total: 0, loadingMore: false }));
      return;
    }
    const offset = append ? this.data.reports.length : 0;
    this.setData({ loading: !append, loadingMore: append, error: '', needsCompetition: false,
      selectedScope: scope, ...(append ? {} : { reports: [], hasReports: false, hasMore: false, total: 0 }) });
    try {
      const payload = await request('/api/battle-reports', { ...scopeParams(scope), limit: 10, offset },
        { forceRefresh: Boolean(options.forceRefresh) });
      if (requestId !== this._requestId || !sameScope(scope, getRequiredScope())) return;
      const reports = (payload.reports || []).map(decorate);
      const nextReports = append ? this.data.reports.concat(reports) : reports;
      this.setData({ reports: nextReports, hasReports: nextReports.length > 0,
        hasMore: Boolean(payload.pagination && payload.pagination.has_more),
        total: Number(payload.pagination && payload.pagination.total || 0) });
    } catch (error) {
      if (requestId !== this._requestId || !sameScope(scope, getRequiredScope())) return;
      this.setData({ error: error.message || '战报加载失败，请重试' });
    } finally {
      if (requestId === this._requestId) this.setData({ loading: false, loadingMore: false });
    }
  },
  openMatch(event) {
    wx.navigateTo({ url: appendScopeToPath(`/pages/match-detail/match-detail?match_id=${encodeURIComponent(event.currentTarget.dataset.id)}`, this.data.selectedScope) });
  },
  openDay(event) {
    wx.navigateTo({ url: appendScopeToPath(`/pages/day-detail/day-detail?played_on=${encodeURIComponent(event.currentTarget.dataset.day)}`, this.data.selectedScope) });
  },
  onImageError(event) {
    const { day, section, match, field, id } = event.currentTarget.dataset;
    const report = this.data.reports[day];
    const group = report && report.sections[section];
    const entry = group && group.matches[match];
    if (!entry || entry.match_id !== id) return;
    if (!['photoUrl', 'guildLogoUrl'].includes(field)) return;
    this.setData({ [`reports[${day}].sections[${section}].matches[${match}].${field}`]: '' });
  }
});
