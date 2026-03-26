"""
[Graph_making_hub]/plotting/smart_layout.py
==========================================
🧠 Smart Layout Engine (v1.0)

[역할]
- 데이터 분포를 분석하여 최적의 범례/라벨 위치를 계산
- Matplotlib 객체 간의 충돌을 방지하고 지능적인 배치 수행
"""

import matplotlib.pyplot as plt
import numpy as np


def find_empty_quadrant(x, y, x_lim=None, y_lim=None):
    """
    데이터 포인트의 밀도를 분석하여 가장 비어 있는 사분면을 찾습니다.
    (0: upper-right, 1: upper-left, 2: lower-left, 3: lower-right)
    """
    if len(x) == 0:
        return 0

    x = np.array(x)
    y = np.array(y)

    x_mid = (np.min(x) + np.max(x)) / 2 if x_lim is None else (x_lim[0] + x_lim[1]) / 2
    y_mid = (np.min(y) + np.max(y)) / 2 if y_lim is None else (y_lim[0] + y_lim[1]) / 2

    quadrants = [0, 0, 0, 0]

    for xi, yi in zip(x, y):
        if xi >= x_mid and yi >= y_mid: quadrants[0] += 1
        elif xi < x_mid and yi >= y_mid: quadrants[1] += 1
        elif xi < x_mid and yi < y_mid: quadrants[2] += 1
        else: quadrants[3] += 1

    return np.argmin(quadrants)

def stagger_labels_2d(y_positions, min_gap=0.05):
    """
    라벨의 Y 좌표가 겹치지 않도록 일정한 간격으로 벌려줍니다. (Athena 이식 로직)
    """
    n = len(y_positions)
    if n <= 1:
        return list(y_positions)

    # (원래 인덱스, Y값) 쌍을 정렬
    pairs = sorted(enumerate(y_positions), key=lambda p: p[1])
    ys = [y for _, y in pairs]

    # 순방향 스윕: 겹침 방지 (위쪽으로 밀기)
    for k in range(1, n):
        if ys[k] - ys[k - 1] < min_gap:
            ys[k] = ys[k - 1] + min_gap

    # 역방향 스윕: 상단 초과분 보정 (1.0 넘어간 경우 아래로 당기기)
    if ys[-1] > 1.0:
        overflow = ys[-1] - 1.0
        for k in range(n - 1, -1, -1):
            ys[k] = ys[k] - overflow
            if k > 0 and ys[k] < ys[k - 1] + min_gap:
                ys[k] = ys[k - 1] + min_gap

    # 결과 복원 (축 범위 [0, 1]로 클램프)
    result = [0.0] * n
    for (orig_idx, _), new_y in zip(pairs, ys):
        result[orig_idx] = max(0.0, min(1.0, new_y))
    return result

def add_leader_line(ax, start_pos, end_pos, style='elbow', **kwargs):
    """
    데이터 포인트와 라벨을 잇는 지시선을 그립니다.
    """
    sx, sy = start_pos
    ex, ey = end_pos

    if style == 'elbow':
        # 꺾임선 (L-path)
        mid_x = (sx + ex) / 2
        xs = [sx, mid_x, mid_x, ex]
        ys = [sy, sy, ey, ey]
    else:
        # 직선
        xs = [sx, ex]
        ys = [sy, ey]

    line = ax.plot(xs, ys, **kwargs)
    return line
