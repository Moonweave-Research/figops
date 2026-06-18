import unittest

from plotting.smart_layout import find_empty_quadrant, stagger_labels_2d


class TestSmartLayout(unittest.TestCase):
    def test_find_empty_quadrant(self):
        # 데이터가 우측 하단에만 있는 경우
        x = [1, 2, 3]
        y = [-1, -2, -3]
        # (x_mid=2, y_mid=-2) 기준, 비어 있는 사분면은 0(UR) 또는 1(UL) 또는 2(LL)
        empty = find_empty_quadrant(x, y)
        self.assertIn(empty, [0, 1, 2])

    def test_stagger_labels_2d(self):
        # 겹치는 Y 좌표들
        y_pos = [0.1, 0.11, 0.12]
        staggered = stagger_labels_2d(y_pos, min_gap=0.05)
        # 간격이 최소 0.05 이상 확보되어야 함 (부동 소수점 오차 고려)
        self.assertGreaterEqual(staggered[1] - staggered[0], 0.0499)
        self.assertGreaterEqual(staggered[2] - staggered[1], 0.0499)

    def test_stagger_labels_2d_crowded_top_no_pileup(self):
        # 상단에 몰린 라벨: 위로 밀린 뒤 아래로 보정될 때 겹쳐 쌓이면 안 됨
        y_pos = [0.90, 0.91, 0.92, 0.93, 0.94]
        staggered = stagger_labels_2d(y_pos, min_gap=0.05)
        # 정렬된 순서로 인접 간격이 모두 min_gap 이상 유지되어야 함
        ordered = sorted(staggered)
        for k in range(1, len(ordered)):
            self.assertGreaterEqual(ordered[k] - ordered[k - 1], 0.0499)
        self.assertLessEqual(max(staggered), 1.0 + 1e-9)
        self.assertGreaterEqual(min(staggered), -1e-9)

    def test_stagger_labels_2d_overflow_compress(self):
        # min_gap으로 다 담을 수 없으면 [0,1]에 균등 분포로 압축
        n = 11
        y_pos = [0.95] * n  # min_gap=0.05 * 10 = 0.5 도 [0,1]에 들어가지만,
        staggered = stagger_labels_2d(y_pos, min_gap=0.2)  # 0.2*10=2.0 > 1.0 → 압축 필요
        ordered = sorted(staggered)
        self.assertAlmostEqual(ordered[0], 0.0, places=6)
        self.assertAlmostEqual(ordered[-1], 1.0, places=6)
        gap = 1.0 / (n - 1)
        for k in range(1, n):
            self.assertAlmostEqual(ordered[k] - ordered[k - 1], gap, places=6)

    def test_find_empty_quadrant_ignores_out_of_range(self):
        # 가시 범위(x_lim/y_lim) 밖 점들은 사분면 집계에서 제외되어야 함.
        # 가시 범위 [0,1]x[0,1], mid=(0.5,0.5).
        # 가시 점: UR(0) 2개, UL(1) 2개, LL(2) 1개, LR(3) 0개 → 진짜 빈 사분면은 LR(3).
        x_in = [0.8, 0.9, 0.2, 0.1, 0.2]
        y_in = [0.8, 0.9, 0.8, 0.9, 0.2]
        # 범위 밖 점 하나가 LR(3)에 위치 → 집계되면 LR=1 로 LL(2)과 동률 → argmin 이 LL(2)로 오답
        x_out = [0.9]
        y_out = [-5.0]
        empty = find_empty_quadrant(x_in + x_out, y_in + y_out, x_lim=(0.0, 1.0), y_lim=(0.0, 1.0))
        # 범위 밖 점을 제외하면 LR(3)이 유일하게 빈 사분면이어야 함
        self.assertEqual(empty, 3)


if __name__ == "__main__":
    unittest.main()
