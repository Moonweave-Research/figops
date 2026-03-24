
import unittest
import numpy as np
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

if __name__ == '__main__':
    unittest.main()
