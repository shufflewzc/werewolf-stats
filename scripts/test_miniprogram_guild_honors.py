import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MiniProgramGuildHonorTests(unittest.TestCase):
    def test_guild_detail_refreshes_when_shown(self):
        source = (ROOT / "miniprogram/pages/guild-detail/guild-detail.js").read_text()

        self.assertIn("onShow()", source)
        self.assertIn("this.loadData({ forceRefresh: true });", source)

    def test_honors_use_a_stable_composite_key(self):
        source = (ROOT / "miniprogram/pages/guild-detail/guild-detail.js").read_text()
        template = (ROOT / "miniprogram/pages/guild-detail/guild-detail.wxml").read_text()

        self.assertIn("function normalizeHonors(items)", source)
        self.assertIn("honors: normalizeHonors(payload.honors)", source)
        self.assertIn('wx:key="key"', template)
        self.assertNotIn('wx:key="title"', template)


if __name__ == "__main__":
    unittest.main()
