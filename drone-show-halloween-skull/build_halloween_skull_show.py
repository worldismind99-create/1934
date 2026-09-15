# -*- coding: utf-8 -*-
"""
ハロウィン・ドローンショー「SKULL」 300機 — Blender 自動構築スクリプト
=====================================================================

素のBlender(Skybrushなし)で、プロ実案件と同じ
「COPY_LOCATION + influence クロスフェード」構造のショーを一から組み立てる。

使い方
  (a) Blender の Scripting ワークスペースでこのテキストを開いて「実行」
  (b) コマンドライン:  blender -b -P build_halloween_skull_show.py
  (c) pip 版 bpy:      python build_halloween_skull_show.py
環境変数
  SHOW_OUT_DIR   出力フォルダ(既定: このスクリプトのあるフォルダ)
  SHOW_SKIP_SAVE "1" で .blend を保存しない

生成物
  Templates/Drone template ... ICO球(42頂点・直径1m)
  Drones/Drone 1..300      ... 機体(各機専用「LED color of Drone N」放射マテリアル)
  Formations/...           ... 各シーンのフォーメーション(エンプティ群+親エンプティ)
  oya/oya.takeoff, oya.show... 会場合わせ用の親エンプティ
  Guides/FlightArea        ... 飛行区域ボックス(110×50×100m・ワイヤー表示・レンダー無効)
  カメラ: AudienceCam(平行投影・観客距離200m) / GroundCam(透視39mm・高さ1.6m・注視点追従)
  タイムラインマーカー(日本語)=尺割り表
  テキストデータブロック: このスクリプト自身 + 検証スクリプト + 尺割りJSON

設計値(スキル「鉄板数値」)
  グリッド30×10・ピッチ3m / 安全距離1.5m / 離陸15秒→20m / 絵柄中心高度65m /
  キャンバス110×50m / 遷移設計速度=上限(5/4/3 m/s)の6割 / 1シーン20〜60秒+暗転
"""
import bpy
import math
import os
import sys
import json
import time
import random

import numpy as np
from mathutils import Vector

# =============================== パラメータ ===============================
N = 300                     # 機体数
FPS = 24
GRID_COLS, GRID_ROWS = 30, 10
GRID_PITCH = 3.0            # 地上グリッド間隔[m]
DRONE_R = 0.5               # 機体半径[m]
SAFE_DIST = 1.5             # 安全距離[m]
FORMATION_MIN_DIST = 1.8    # フォーメーション設計時の最小点間隔[m](安全距離+余裕)
TAKEOFF_ALT = 20.0
TAKEOFF_SEC = 15
CENTER = np.array([0.0, 0.0, 65.0])   # 絵柄の中心(観客は -Y 側)
CANVAS_W, CANVAS_H = 110.0, 50.0
V_DESIGN = {"xy": 3.0, "up": 2.4, "down": 1.8}   # 遷移設計速度(上限 5/4/3 の 6割)
EASE_PEAK = 1.5             # ベジエ(イーズイン/アウト)のピーク速度/平均速度
N_STARS = 90                # 星空間奏の点灯機数
SKULL_SCALE = 1.25          # スカル全体の倍率(1.0 = 幅26m → 1.25 = 幅33m)
SHOW_MODE = os.environ.get("SHOW_MODE", "30s")   # "30s": 本編30秒のスカル単独 / "full": 7ページ約8分
CONTENT_SEC = 30            # 30s モードの本編尺
SEED = 1934
SHOW_NAME = "20261031_Halloween_SKULL_Animation_v01"

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
OUT_DIR = os.environ.get("SHOW_OUT_DIR", HERE)

rng = random.Random(SEED)
nprng = np.random.default_rng(SEED)

# =============================== 色パレット ===============================
BLACK = (0.0, 0.0, 0.0)
COL = {
    "purple": (0.55, 0.10, 1.00),
    "orange": (1.00, 0.35, 0.02),
    "pumpkin": (0.70, 0.16, 0.00),
    "candle": (1.00, 0.92, 0.40),
    "stem": (0.20, 0.85, 0.15),
    "green": (0.15, 1.00, 0.25),
    "teeth": (0.70, 1.00, 0.75),
    "red": (1.00, 0.02, 0.02),
    "blue": (0.10, 0.30, 1.00),
    "cyan": (0.20, 0.80, 1.00),
    "white": (1.00, 1.00, 1.00),
    "amber": (1.00, 0.55, 0.05),
    "mist": (0.40, 0.05, 0.70),
}


def sec(s):
    return int(round(s * FPS))


# =============================== 幾何ユーティリティ ===============================
def fib_sphere(n):
    """単位球面上のフィボナッチ点列(均等分布)"""
    i = np.arange(n) + 0.5
    phi = np.arccos(1.0 - 2.0 * i / n)
    theta = math.pi * (1.0 + 5 ** 0.5) * i
    return np.stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)], 1)


def sample_polyline(pts, spacing, closed=False):
    """ポリライン上を等間隔にサンプリング(端点を含む)"""
    pts = np.asarray(pts, float)
    if closed:
        pts = np.vstack([pts, pts[:1]])
    seg = np.diff(pts, axis=0)
    L = np.linalg.norm(seg, axis=1)
    total = float(L.sum())
    n = max(1, int(math.floor(total / spacing + 1e-6)))   # 実間隔 >= spacing を保証
    ds = np.linspace(0.0, total, n + 1)
    if closed:
        ds = ds[:-1]
    cum = np.concatenate([[0.0], np.cumsum(L)])
    out = []
    for d in ds:
        k = int(min(np.searchsorted(cum, d, side="right") - 1, len(L) - 1))
        t = (d - cum[k]) / L[k] if L[k] > 0 else 0.0
        out.append(pts[k] + t * seg[k])
    return np.array(out)


def dedupe(pts, min_d):
    """min_d 未満に近い点を貪欲に間引く(先に来た点を優先)"""
    keep = []
    for p in pts:
        if not keep:
            keep.append(p)
            continue
        K = np.array(keep)
        if np.min(np.linalg.norm(K - p, axis=1)) >= min_d:
            keep.append(p)
    return np.array(keep) if keep else np.zeros((0, 3))


def filter_against(pts, existing, min_d):
    """existing の点群から min_d 未満にある点を除く"""
    P = np.asarray(pts, float).reshape(-1, 3)
    if len(P) == 0 or len(existing) == 0:
        return P
    E = np.asarray(existing, float).reshape(-1, 3)
    d = np.linalg.norm(P[:, None, :] - E[None, :, :], axis=2).min(1)
    return P[d >= min_d]


def min_pair_dist(pts):
    if len(pts) < 2:
        return 1e9
    P = np.asarray(pts)
    d = np.linalg.norm(P[:, None, :] - P[None, :, :], axis=2)
    np.fill_diagonal(d, 1e9)
    return float(d.min())


def point_in_poly(x, z, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        if (z1 > z) != (z2 > z):
            xi = x1 + (z - z1) * (x2 - x1) / (z2 - z1)
            if xi > x:
                inside = not inside
    return inside


def dist_to_segments(x, z, poly, closed=True):
    P = np.array(poly, float)
    Q = np.vstack([P, P[:1]]) if closed else P
    a, b = Q[:-1], Q[1:]
    ab = b - a
    ap = np.array([x, z]) - a
    t = np.clip((ap * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-9), 0, 1)
    c = a + t[:, None] * ab
    return float(np.min(np.linalg.norm(c - np.array([x, z]), axis=1)))


def hex_fill(poly, spacing, margin, holes=()):
    """多角形内部を六方格子で埋める(境界からmarginは空ける)"""
    P = np.array(poly, float)
    xmin, xmax = P[:, 0].min(), P[:, 0].max()
    zmin, zmax = P[:, 1].min(), P[:, 1].max()
    out = []
    dz = spacing * math.sqrt(3) / 2
    row = 0
    z = zmin
    while z <= zmax:
        x = xmin + (spacing / 2 if row % 2 else 0)
        while x <= xmax:
            if point_in_poly(x, z, poly) and dist_to_segments(x, z, poly) >= margin:
                ok = True
                for h in holes:
                    if point_in_poly(x, z, h) or dist_to_segments(x, z, h) < margin:
                        ok = False
                        break
                if ok:
                    out.append((x, z))
            x += spacing
        z += dz
        row += 1
    return out


def rot_z(pts, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    P = np.asarray(pts, float).copy()
    x, y = P[:, 0].copy(), P[:, 1].copy()
    P[:, 0] = c * x - s * y
    P[:, 1] = s * x + c * y
    return P


# =============================== 割り当て(ハンガリアン法) ===============================
def hungarian(cost):
    """cost[n, m] (n<=m) の最小コスト割り当て。返り値: 各行に対する列番号"""
    cost = np.asarray(cost, float)
    n, m = cost.shape
    assert n <= m
    INF = 1e18
    u = np.zeros(n + 1)
    v = np.zeros(m + 1)
    p = np.zeros(m + 1, dtype=int)
    way = np.zeros(m + 1, dtype=int)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = np.full(m + 1, INF)
        used = np.zeros(m + 1, dtype=bool)
        while True:
            used[j0] = True
            i0 = p[j0]
            cur = cost[i0 - 1] - u[i0] - v[1:]
            mask = ~used[1:]
            better = mask & (cur < minv[1:])
            mv = minv[1:]
            mv[better] = cur[better]
            wy = way[1:]
            wy[better] = j0
            cand = np.where(mask, minv[1:], INF)
            j1 = int(np.argmin(cand)) + 1
            delta = cand[j1 - 1]
            u[p[used]] += delta
            v[used] -= delta
            minv[~used] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    ans = np.zeros(n, dtype=int)
    for j in range(1, m + 1):
        if p[j] > 0:
            ans[p[j] - 1] = j - 1
    return ans


def transition_seconds(src, dst):
    """直線クロスフェードで必要な遷移秒数(設計速度・イーズピーク係数込み)"""
    d = np.asarray(dst) - np.asarray(src)
    dxy = np.linalg.norm(d[:, :2], axis=1)
    dz = d[:, 2]
    t_xy = EASE_PEAK * dxy / V_DESIGN["xy"]
    t_up = EASE_PEAK * np.maximum(dz, 0) / V_DESIGN["up"]
    t_dn = EASE_PEAK * np.maximum(-dz, 0) / V_DESIGN["down"]
    t = float(np.max(np.maximum.reduce([t_xy, t_up, t_dn]))) if len(d) else 0.0
    return max(6.0, math.ceil(t))


# =============================== フォーメーション設計 ===============================
def make_stars(n, seed, box=(52, 12, 24), min_d=6.0):
    """箱の中にまばらな星。返り値: (n,3) ローカル座標"""
    r = np.random.default_rng(seed)
    pts = []
    tries = 0
    while len(pts) < n and tries < 200000:
        tries += 1
        p = (r.uniform(-box[0], box[0]), r.uniform(-box[1], box[1]), r.uniform(-box[2], box[2]))
        if not pts or np.min(np.linalg.norm(np.array(pts) - p, axis=1)) >= min_d:
            pts.append(p)
    return np.array(pts)


def make_pumpkin():
    """ジャック・オー・ランタン(3D)。返り値: dict(parts={name: (pts, color)})"""
    PR = np.array([19.0, 17.0, 14.5])
    PF = 1.22   # 顔パーツの倍率(本体拡大に合わせる)

    def lift(x, z):
        v = 1 - (x / PR[0]) ** 2 - (z / PR[2]) ** 2
        return -PR[1] * math.sqrt(max(v, 0.0))

    eyeL = [(-11.5, 1.5), (-4.0, 1.5), (-7.5, 8.5)]
    eyeR = [(4.0, 1.5), (11.5, 1.5), (7.5, 8.5)]
    nose = [(-2.5, -2.0), (2.5, -2.0), (0.0, 2.2)]
    mouth = [(-12, -4.5), (-9, -6.8), (-6, -4.5), (-3, -6.8), (0, -4.5), (3, -6.8), (6, -4.5),
             (9, -6.8), (12, -4.5), (9.5, -8.5), (5, -10.0), (0, -10.4), (-5, -10.0), (-9.5, -8.5)]
    feats = [[(x * PF, z * PF) for x, z in poly] for poly in (eyeL, eyeR, nose, mouth)]
    face = []
    for poly in feats:
        for x, z in sample_polyline(poly, 2.3, closed=True):
            face.append((x, lift(x, z), z))
        for x, z in hex_fill(poly, 3.0, 1.8):
            face.append((x, lift(x, z), z))
    face = dedupe(np.array(face), FORMATION_MIN_DIST)

    # 茎
    top = PR[2]
    stem = []
    for k in range(6):
        a = 2 * math.pi * k / 6
        stem.append((1.9 * math.cos(a), 1.9 * math.sin(a), top + 0.6))
    for k in range(5):
        a = 2 * math.pi * k / 5 + 0.3
        stem.append((1.7 * math.cos(a) + 0.5, 1.7 * math.sin(a), top + 3.2))
    stem.append((1.4, -0.4, top + 5.4))
    stem = np.array(stem)

    n_body_target = N - len(face) - len(stem)

    def body_for(nb):
        P = fib_sphere(nb)
        ang = np.arctan2(P[:, 1], P[:, 0])
        P = P * PR * (1 + 0.035 * np.cos(6 * ang))[:, None]   # かぼちゃの筋(6弁)
        keep = []
        for p in P:
            if p[1] < 0:  # 前面: 顔の穴を空ける
                bad = False
                for poly in feats:
                    if point_in_poly(p[0], p[2], poly) or dist_to_segments(p[0], p[2], poly) < 2.4:
                        bad = True
                        break
                if bad:
                    continue
            if p[2] > top - 1.5 and math.hypot(p[0], p[1]) < 3.4:
                continue  # 茎の場所
            keep.append(p)
        K = filter_against(np.array(keep), np.vstack([face, stem]), FORMATION_MIN_DIST)
        return dedupe(K, FORMATION_MIN_DIST)

    lo, hi = n_body_target, n_body_target * 3
    best = None
    for _ in range(40):
        mid = (lo + hi) // 2
        B = body_for(mid)
        if len(B) < n_body_target:
            lo = mid + 1
        else:
            best = B
            hi = mid
        if hi - lo <= 0:
            break
    B = body_for(hi) if best is None else best
    B = B[:n_body_target] if len(B) >= n_body_target else B
    parts = {
        "body": (B, COL["pumpkin"]),
        "face": (face, COL["candle"]),
        "stem": (stem, COL["stem"]),
    }
    return parts


def make_skull():
    """スカル(3D)。頭蓋+顔面+眼窩+鼻腔+頬骨+上歯+下顎(別パーツ)"""
    CR = np.array([13.0, 13.5, 12.5])
    CC = np.array([0.0, 0.5, 6.0])
    socketC = [(-5.6, 2.2), (5.6, 2.2)]
    socketR = 4.2
    nose = [(-2.3, -5.2), (2.3, -5.2), (0.0, -0.3)]

    def face_y(x, z):
        return -10.0 - 0.12 * (-2.5 - z) + 0.05 * x * x

    def front_y(x, z):
        if z >= -2.0:
            v = 1 - ((x - CC[0]) / CR[0]) ** 2 - ((z - CC[2]) / CR[2]) ** 2
            return CC[1] - CR[1] * math.sqrt(max(v, 0.0))
        return face_y(x, z)

    def in_feature(x, z, margin):
        for cx, cz in socketC:
            if math.hypot(x - cx, z - cz) < socketR + margin:
                return True
        if point_in_poly(x, z, nose) or dist_to_segments(x, z, nose) < margin:
            return True
        return False

    # --- 眼窩リング・目・鼻腔 ---
    sockets, eyes, nose_pts = [], [], []
    for cx, cz in socketC:
        for k in range(11):
            a = 2 * math.pi * k / 11 + 0.1
            x, z = cx + socketR * math.cos(a), cz + socketR * math.sin(a)
            sockets.append((x, front_y(x, z), z))
        for ox, oz in ((0.0, 1.1), (-0.95, -0.55), (0.95, -0.55)):   # 赤い目=3機の小三角
            eyes.append((cx + ox, front_y(cx, cz) + 3.5, cz + oz))
    for x, z in sample_polyline(nose, 2.2, closed=True):
        nose_pts.append((x, front_y(x, z), z))
    sockets = np.array(sockets)
    eyes = np.array(eyes)
    nose_pts = dedupe(np.array(nose_pts), FORMATION_MIN_DIST)
    acc = np.vstack([sockets, eyes, nose_pts])

    # --- 顔面(上顎)プレート ---
    faceP = []
    for x, z in hex_fill([(-9.5, -2.6), (9.5, -2.6), (7.8, -9.2), (-7.8, -9.2)], 2.4, 0.5):
        if in_feature(x, z, 1.2):
            continue
        faceP.append((x, face_y(x, z), z))
    faceP = dedupe(filter_against(np.array(faceP), acc, FORMATION_MIN_DIST), FORMATION_MIN_DIST)
    acc = np.vstack([acc, faceP])

    # --- 頬骨(左右) ---
    cheeks = []
    for sgn in (-1, 1):
        pl = [(sgn * 10.4, -6.0, -1.8), (sgn * 11.9, -4.4, -3.4), (sgn * 12.3, -2.6, -6.0), (sgn * 10.8, -4.0, -8.8)]
        cheeks.extend(sample_polyline(pl, 2.4).tolist())
    cheeks = filter_against(np.array(cheeks), acc, FORMATION_MIN_DIST)
    acc = np.vstack([acc, cheeks])

    # --- 上歯 ---
    upper = []
    for x in (-7.4, -5.3, -3.2, -1.1, 1.1, 3.2, 5.3, 7.4):
        upper.append((x, face_y(x, -11.0) - 0.3, -11.0))
    upper = filter_against(np.array(upper), acc, FORMATION_MIN_DIST)
    acc = np.vstack([acc, upper])

    # --- 下顎(ピボット (0,1,-7) 回りに回転させる別パーツ) ---
    jaw = []
    for phi in np.linspace(math.radians(200), math.radians(340), 13):
        x, y = 11.5 * math.cos(phi), 1.0 + 12.8 * math.sin(phi)
        jaw.append((x, y, -16.3 + 4.6 * abs(math.cos(phi))))
    for sgn in (-1, 1):
        jaw.append((sgn * 11.4, -1.2, -9.4))
        jaw.append((sgn * 11.7, 0.6, -7.2))
    lower = []
    for phi in np.linspace(math.radians(207), math.radians(333), 8):
        lower.append((9.3 * math.cos(phi), 1.0 + 12.0 * math.sin(phi), -12.9))
    jaw = np.array(jaw)
    lower = np.array(lower)
    acc = np.vstack([acc, jaw, lower])

    # 紫の霧(スカルの下に漂う・薄く明滅)
    mist = make_stars(30, SEED + 9, box=(22, 6, 3), min_d=4.0) + np.array([0, 0, -23.5])
    acc = np.vstack([acc, mist])

    fixed_named = {
        "sockets": (sockets, COL["green"]),
        "eyes": (eyes, COL["red"]),
        "nose": (nose_pts, COL["green"]),
        "face": (faceP, COL["green"]),
        "cheeks": (cheeks, COL["green"]),
        "upper_teeth": (upper, COL["teeth"]),
        "mist": (mist, COL["mist"]),
    }
    n_fixed = sum(len(v[0]) for v in fixed_named.values()) + len(jaw) + len(lower)
    n_cr_target = N - n_fixed
    others = acc

    def cranium_for(nc):
        P = fib_sphere(nc) * CR + CC
        keep = []
        for p in P:
            x, y, z = p
            if not (z >= -1.5 or (y >= 2.5 and z >= -7.5)):
                continue
            if in_feature(x, z, 1.4):
                continue   # 眼窩・鼻腔は貫通させる(背面の点で穴が埋まらないように)
            if y < 0 and z < -1.0 and abs(x) < 9.8:
                continue  # 顔面プレートに譲る
            keep.append(p)
        K = filter_against(np.array(keep), others, FORMATION_MIN_DIST)   # 他パーツと近い点を捨てる
        return dedupe(K, FORMATION_MIN_DIST)

    lo, hi = n_cr_target, n_cr_target * 3
    best = None
    for _ in range(40):
        mid = (lo + hi) // 2
        K = cranium_for(mid)
        if len(K) < n_cr_target:
            lo = mid + 1
        else:
            best = K
            hi = mid
        if hi - lo <= 0:
            break
    K = cranium_for(hi) if best is None else best
    K = K[:n_cr_target]
    parts = dict(fixed_named)
    parts["cranium"] = (K, COL["green"])
    jaw_parts = {"jaw": (jaw, COL["green"]), "lower_teeth": (lower, COL["teeth"])}
    SK = SKULL_SCALE
    parts = {k: (np.asarray(v[0]) * SK, v[1]) for k, v in parts.items()}
    jaw_parts = {k: (np.asarray(v[0]) * SK, v[1]) for k, v in jaw_parts.items()}
    return parts, jaw_parts


def make_bat():
    """コウモリ(正面平面+翼は別パーツで羽ばたき)"""
    wing = [(4, 8), (9, 13), (16, 17), (24, 19.5), (32, 20), (37, 19), (41, 17),
            (39, 12), (36, 6), (33, 1), (30, -3),
            (27, 2), (24, 4), (21, 1), (18, -3),
            (16, 0), (13, 2), (11, -1), (9, -4),
            (7, -2), (5, 0), (4, 3)]
    fingers = [[(4, 8), (41, 17)], [(4, 8), (30, -3)], [(4, 8), (18, -3)], [(4, 8), (9, -4)]]

    def wing_pts(fill_spacing):
        pts = [(x, 0.0, z) for x, z in sample_polyline(wing, 2.3, closed=True)]
        for f in fingers:
            S = sample_polyline(f, 3.0)
            for x, z in S:
                if math.hypot(x - 4, z - 8) > 3.0 and dist_to_segments(x, z, wing) > 1.8:
                    pts.append((x, 0.0, z))
        fill = []
        for x, z in hex_fill(wing, fill_spacing, 2.0):
            if min(dist_to_segments(x, z, f, closed=False) for f in fingers) >= 1.9:
                fill.append((x, 0.0, z))
        P = np.array(pts + fill)
        return dedupe(P, FORMATION_MIN_DIST)

    head = [(4.0 * math.cos(a), -2.0, 9.0 + 4.0 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 12, endpoint=False)]
    ears = []
    for sgn in (-1, 1):
        ears.extend([(x, -2.0, z) for x, z in sample_polyline([(sgn * 4.2, 11.6), (sgn * 3.2, 17.5), (sgn * 0.9, 12.9)], 2.2)])
    body = [(4.5 * math.cos(a), -2.0, 1.0 + 8.0 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 17, endpoint=False)]
    feet = []
    for sgn in (-1, 1):
        feet.extend([(x, -2.0, z) for x, z in sample_polyline([(sgn * 2.6, -7.0), (sgn * 4.2, -11.5)], 2.3)])
    eyes = [(-1.6, -3.8, 10.2), (1.6, -3.8, 10.2)]
    core = dedupe(np.array(head + ears + body + feet), FORMATION_MIN_DIST)
    n_wing_target = (N - len(core) - len(eyes)) // 2

    lo, hi = 1.9, 8.0
    W = None
    for _ in range(30):
        mid = (lo + hi) / 2
        Wt = wing_pts(mid)
        if len(Wt) > n_wing_target:
            lo = mid
        else:
            W = Wt
            hi = mid
        if hi - lo < 0.02:
            break
    if W is None:
        W = wing_pts(hi)
    W = W[:n_wing_target]
    W = filter_against(W, np.vstack([core, np.array(eyes)]), FORMATION_MIN_DIST)
    WL = W.copy()
    WL[:, 0] *= -1
    fixed = {"body": (core, COL["blue"]), "eyes": (np.array(eyes), COL["red"])}
    wings = {"wingR": (W, COL["blue"]), "wingL": (WL, COL["blue"])}
    return fixed, wings


STROKE_FONT = {
    "H": [[(0, 0), (0, 1.4)], [(1, 0), (1, 1.4)], [(0, 0.7), (1, 0.7)]],
    "A": [[(0, 0), (0.5, 1.4), (1, 0)], [(0.22, 0.6), (0.78, 0.6)]],
    "P": [[(0, 0), (0, 1.4), (0.72, 1.4), (1, 1.18), (1, 0.92), (0.72, 0.7), (0, 0.7)]],
    "Y": [[(0, 1.4), (0.5, 0.75), (1, 1.4)], [(0.5, 0.75), (0.5, 0)]],
    "L": [[(0, 1.4), (0, 0), (1, 0)]],
    "O": [[(0.5 + 0.5 * math.cos(a), 0.7 + 0.7 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 17)]],
    "W": [[(0, 1.4), (0.25, 0), (0.5, 0.95), (0.75, 0), (1, 1.4)]],
    "E": [[(1, 1.4), (0, 1.4), (0, 0), (1, 0)], [(0, 0.7), (0.8, 0.7)]],
    "N": [[(0, 0), (0, 1.4), (1, 0), (1, 1.4)]],
}


def make_text(lines=("HAPPY", "HALLOWEEN"), letter_h=14.0, line_gap=6.0):
    """単線ストロークフォントで文字列を点列化。余った機体は周囲のスパークル"""
    scale = letter_h / 1.4
    adv = 1.28 * scale
    total_h = len(lines) * letter_h + (len(lines) - 1) * line_gap
    rows = []
    for li, text in enumerate(lines):
        z0 = total_h / 2 - letter_h - li * (letter_h + line_gap)
        width = len(text) * adv - 0.28 * scale
        x0 = -width / 2
        for ci, ch in enumerate(text):
            for stroke in STROKE_FONT[ch]:
                P = [(x0 + ci * adv + x * scale, z0 + z * scale) for x, z in stroke]
                rows.append((li, ci, P))

    def build(spacing):
        pts, letter_id = [], []
        for li, ci, P in rows:
            closed = (P[0] == P[-1])
            S = sample_polyline(P[:-1] if closed else P, spacing, closed=closed)
            for x, z in S:
                pts.append((x, 0.0, z))
                letter_id.append(li * 100 + ci)
        P = np.array(pts)
        keep = []
        for k, p in enumerate(P):
            if not keep or np.min(np.linalg.norm(P[keep] - p, axis=1)) >= FORMATION_MIN_DIST:
                keep.append(k)
        return P[keep], [letter_id[k] for k in keep]

    lo, hi = 1.8, 4.0
    best = None
    for _ in range(30):
        mid = (lo + hi) / 2
        P, ids = build(mid)
        if len(P) > N - 20:
            lo = mid
        else:
            best = (P, ids, mid)
            hi = mid
        if hi - lo < 0.01:
            break
    P, ids, spacing = best
    # スパークル(余り機体)
    n_sp = N - len(P)
    sp = []
    r = np.random.default_rng(SEED + 7)
    tries = 0
    while len(sp) < n_sp and tries < 100000:
        tries += 1
        q = np.array([r.uniform(-54, 54), r.uniform(-6, 6), r.uniform(-24, 24)])
        if np.min(np.linalg.norm(P - q, axis=1)) < 5.0:
            continue
        if sp and np.min(np.linalg.norm(np.array(sp) - q, axis=1)) < 5.0:
            continue
        sp.append(q)
    return {"text": (P, COL["white"]), "sparkle": (np.array(sp), COL["amber"])}, ids, spacing


# =============================== Blender 構築 ===============================
def collection(name, parent=None):
    col = bpy.data.collections.get(name)
    if not col:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def new_empty(name, col, loc=(0, 0, 0), parent=None, size=0.3, dtype="PLAIN_AXES"):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = size
    e.empty_display_type = dtype
    e.location = loc
    if parent is not None:
        e.parent = parent
    col.objects.link(e)
    return e


def clear_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for blk in (bpy.data.meshes, bpy.data.materials, bpy.data.actions, bpy.data.cameras, bpy.data.texts):
        for x in list(blk):
            blk.remove(x)


def setup_scene(frame_end):
    scene = bpy.context.scene
    scene.name = "HalloweenSkullShow"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.fps = 24
    scene.frame_start = 0
    scene.frame_end = frame_end
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    try:
        scene.eevee.taa_render_samples = 64
        scene.eevee.taa_samples = 16
    except Exception:
        pass
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 900
    try:   # pip版bpyなど FFMPEG 非搭載ビルドでは PNG 連番にフォールバック
        scene.render.image_settings.file_format = "FFMPEG"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
        scene.render.ffmpeg.audio_codec = "NONE"
    except TypeError:
        scene.render.image_settings.file_format = "PNG"
    scene.render.use_motion_blur = False
    scene.render.filepath = f"//render/{SHOW_NAME}"

    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg:
        bg.inputs[0].default_value = (0, 0, 0, 1)
        bg.inputs[1].default_value = 1.0

    # ---- コンポジット: グレア(Bloom) ----
    try:
        scene.render.use_compositing = True
        if hasattr(scene, "compositing_node_group"):      # Blender 5.x
            nt = scene.compositing_node_group
            if nt is None:
                nt = bpy.data.node_groups.new("Compositing", "CompositorNodeTree")
                scene.compositing_node_group = nt
        else:                                              # Blender 4.x
            scene.use_nodes = True
            nt = scene.node_tree
        if not any(n.type == "GLARE" for n in nt.nodes):
            rl = next((n for n in nt.nodes if n.type == "R_LAYERS"), None) or nt.nodes.new("CompositorNodeRLayers")
            glare = nt.nodes.new("CompositorNodeGlare")
            if hasattr(glare, "glare_type"):
                glare.glare_type = "BLOOM"
            if "Type" in glare.inputs:                       # Blender 5.x はソケット
                try:
                    glare.inputs["Type"].default_value = "Bloom"
                except Exception:
                    pass
            for k, v in {"Threshold": 0.4, "Smoothness": 0.1, "Strength": 2.8, "Size": 0.5}.items():
                if k in glare.inputs:
                    glare.inputs[k].default_value = v
            for k, v in (("threshold", 0.4), ("mix", 0.0), ("size", 7)):
                if hasattr(glare, k):
                    try:
                        setattr(glare, k, v)
                    except Exception:
                        pass
            out = next((n for n in nt.nodes if n.type in ("COMPOSITE", "GROUP_OUTPUT")), None)
            if out is None:
                try:
                    out = nt.nodes.new("CompositorNodeComposite")
                except RuntimeError:
                    out = nt.nodes.new("NodeGroupOutput")
                    if hasattr(nt, "interface"):
                        nt.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
            nt.links.new(rl.outputs["Image"], glare.inputs["Image"])
            nt.links.new(glare.outputs[0], out.inputs[0])
    except Exception as ex:  # コンポジターは無くてもショー自体には影響しない
        print("compositor setup skipped:", ex)
    return scene


def setup_cameras(scene, oya_show):
    col = collection("Cameras")
    # 観客視点(平行投影)
    cd = bpy.data.cameras.new("AudienceCam")
    cd.type = "ORTHO"
    cd.ortho_scale = CANVAS_W + 65
    cd.clip_end = 1000
    cam = bpy.data.objects.new("AudienceCam", cd)
    cam.location = (0, -200, CENTER[2])
    cam.rotation_euler = (math.pi / 2, 0, 0)
    col.objects.link(cam)
    scene.camera = cam
    # スカル拡大用(平行投影・狭画角)
    cd2 = bpy.data.cameras.new("DetailCam")
    cd2.type = "ORTHO"
    cd2.ortho_scale = 70
    cd2.clip_end = 1000
    cam2 = bpy.data.objects.new("DetailCam", cd2)
    cam2.location = (0, -200, CENTER[2])
    cam2.rotation_euler = (math.pi / 2, 0, 0)
    col.objects.link(cam2)
    # 地上の観客目線(透視39mm・高さ1.6m・注視点追従)
    gaze = new_empty("注視点", col, loc=tuple(CENTER), parent=oya_show, size=2, dtype="SPHERE")
    cd3 = bpy.data.cameras.new("GroundCam")
    cd3.type = "PERSP"
    cd3.lens = 39
    cd3.clip_end = 1000
    cam3 = bpy.data.objects.new("GroundCam", cd3)
    cam3.location = (0, -170, 1.6)
    col.objects.link(cam3)
    tr = cam3.constraints.new("TRACK_TO")
    tr.target = gaze
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    for scr in bpy.data.screens:
        for area in scr.areas:
            if area.type == "VIEW_3D":
                for sp in area.spaces:
                    if sp.type == "VIEW_3D":
                        sp.clip_end = 1000
    return cam, cam2, cam3


def add_flight_area():
    col = collection("Guides")
    bpy.ops.mesh.primitive_cube_add(size=1)
    box = bpy.context.active_object
    box.name = "FlightArea 110x50x100m"
    box.scale = (CANVAS_W, 50, 100)
    box.location = (0, 0, 20 + 50)
    for c in box.users_collection:
        c.objects.unlink(box)
    col.objects.link(box)
    box.display_type = "WIRE"
    box.hide_render = True
    mat = bpy.data.materials.new("FlightArea guide")
    mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        bsdf.inputs["Alpha"].default_value = 0.03
    try:
        mat.blend_method = "BLEND"
    except Exception:
        pass
    box.data.materials.append(mat)
    return box


class ShowBuilder:
    def __init__(self):
        self.drones = []
        self.mats = []
        self.led = [[] for _ in range(N)]          # (frame, rgb, interp)
        self.lit_frames = np.zeros(N)              # 点灯時間の集計(ローテーション用)
        self.markers = []
        self.formations = {}
        self.pages = []                            # 尺割り表
        self.frame = 0
        self.con_count = np.zeros(N, dtype=int)

    # ---------- 基礎 ----------
    def build_base(self):
        col_tpl = collection("Templates")
        col_dr = collection("Drones")
        col_form = collection("Formations")
        col_oya = collection("oya")
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=DRONE_R)
        tpl = bpy.context.active_object
        tpl.name = "Drone template"
        for c in tpl.users_collection:
            c.objects.unlink(tpl)
        col_tpl.objects.link(tpl)
        tpl.hide_render = True
        tpl.hide_viewport = True

        self.oya_takeoff = new_empty("oya.takeoff", col_oya, size=3, dtype="ARROWS")
        self.oya_show = new_empty("oya.show", col_oya, size=3, dtype="ARROWS")
        col_grid = collection("Takeoff grid", col_form)
        x0 = -(GRID_COLS - 1) * GRID_PITCH / 2
        y0 = -(GRID_ROWS - 1) * GRID_PITCH / 2
        self.grid = []
        for i in range(N):
            r, c = divmod(i, GRID_COLS)
            pos = (x0 + c * GRID_PITCH, y0 + r * GRID_PITCH, 0.0)
            ge = new_empty(f"Takeoff grid - {i + 1}", col_grid, loc=pos, parent=self.oya_takeoff)
            self.grid.append(ge)
            d = bpy.data.objects.new(f"Drone {i + 1}", tpl.data.copy())
            d.location = pos
            col_dr.objects.link(d)
            mat = bpy.data.materials.new(f"LED color of Drone {i + 1}")
            mat.use_nodes = True
            nt = mat.node_tree
            nt.nodes.clear()
            em = nt.nodes.new("ShaderNodeEmission")
            em.name = "Emission"
            em.inputs[0].default_value = (0, 0, 0, 1)
            em.inputs[1].default_value = 1.0
            out = nt.nodes.new("ShaderNodeOutputMaterial")
            nt.links.new(em.outputs[0], out.inputs[0])
            d.data.materials.append(mat)
            con = d.constraints.new("COPY_LOCATION")
            con.name = "Target[ground]"
            con.target = ge
            con.influence = 1.0
            d.keyframe_insert(f'constraints["{con.name}"].influence', frame=-1)
            self.drones.append(d)
            self.mats.append(mat)
        # 離陸: 親を 0→20m
        self.oya_takeoff.location = (0, 0, 0)
        self.oya_takeoff.keyframe_insert("location", frame=0)
        self.oya_takeoff.location = (0, 0, TAKEOFF_ALT)
        self.oya_takeoff.keyframe_insert("location", frame=sec(TAKEOFF_SEC))
        self.marker("離陸(消灯)", 0)
        self.frame = sec(TAKEOFF_SEC)
        for i in range(N):
            self.led[i].append((-1, BLACK, "CONSTANT"))

    def marker(self, name, frame):
        self.markers.append((name, frame))

    # ---------- フォーメーション ----------
    def add_formation(self, name, parts, pivots=None):
        """parts: {part: (local_pts(n,3), color)} / pivots: {part: (pivot_xyz, parent_part_name or None)}
        親エンプティ <name> を CENTER に置き、各パーツ点をエンプティ化。返り値: dict"""
        col = collection(name, collection("Formations"))
        root = new_empty(name, col, loc=tuple(CENTER), parent=self.oya_show, size=2, dtype="ARROWS")
        pivots = pivots or {}
        pivot_objs = {}
        # ピボット生成(親ピボット指定 parent_part があれば、その部位のピボットの子にする)
        def ensure_pivot(part):
            pv, parent_part = pivots[part]
            key = tuple(pv)
            if key in pivot_objs:
                return pivot_objs[key]
            parent_obj, base = root, np.zeros(3)
            if parent_part is not None and parent_part in pivots:
                parent_obj = ensure_pivot(parent_part)
                base = np.array(pivots[parent_part][0], float)
            pivot_objs[key] = new_empty(f"{name}.{part}.pivot", col, loc=tuple(np.array(pv, float) - base),
                                        parent=parent_obj, size=1.5, dtype="ARROWS")
            return pivot_objs[key]
        for part in pivots:
            ensure_pivot(part)
        empties, colors, part_of = [], [], []
        for part, (pts, color) in parts.items():
            parent = root
            if part in pivots:
                pv, _ = pivots[part]
                parent = pivot_objs[tuple(pv)]
                base = np.array(pv, float)
            else:
                base = np.zeros(3)
            for k, p in enumerate(np.asarray(pts)):
                e = new_empty(f"{name}.{part}.{k}", col, loc=tuple(np.asarray(p) - base), parent=parent)
                empties.append(e)
                colors.append(color)
                part_of.append(part)
        allpts = np.vstack([np.asarray(v[0]) for v in parts.values() if len(v[0])])
        md = min_pair_dist(allpts)
        # 余り機体の駐機位置(絵の後ろ側・消灯)
        n_park = N - len(empties)
        park = []
        for k in range(n_park):
            r, c = divmod(k, 12)
            park.append((-22 + c * 4.0, 30.0 + r * 4.0, -10.0 + (k % 3) * 2.0))
        for k, p in enumerate(park):
            e = new_empty(f"{name}.park.{k}", col, loc=p, parent=root)
            empties.append(e)
            colors.append(BLACK)
            part_of.append("park")
        rest = np.vstack([np.asarray(v[0]).reshape(-1, 3) for v in parts.values() if len(v[0])] + [np.array(park).reshape(-1, 3)]) + CENTER
        f = {"name": name, "root": root, "pivots": pivot_objs, "empties": empties, "rest_world": rest,
             "colors": colors, "part": part_of, "n_lit": len(empties) - n_park, "min_dist": md}
        self.formations[name] = f
        print(f"  formation {name}: {f['n_lit']} pts (+{n_park} park), min spacing {md:.2f} m")
        return f

    # ---------- 遷移計画: 多機体シミュレーション ----------
    # 各機は「直線上をスムーズステップで進む参照点」を追従しつつ、近傍機体から反発を受けて
    # 回り込む。速度(水平3.0/上昇2.4/下降1.8 m/s)と加速度(3.8 m/s²)をクリップ。
    # 得られた軌道は機体ごとの「パス・エンプティ」に焼き込み(プロ300機案件のベイク方式)、
    # 機体は COPY_LOCATION の influence 切替でパス→フォーメーション・スロットを乗り継ぐ。
    R_REP, K_REP, PREDICT = 2.8, 6.0, 0.8
    K_TRACK, C_TRACK, A_TRACK, A_MAX = 2.0, 2.8, 2.6, 3.8
    LOG_STEP = 3

    def _init_plan(self):
        x0 = -(GRID_COLS - 1) * GRID_PITCH / 2
        y0 = -(GRID_ROWS - 1) * GRID_PITCH / 2
        self.grid_pos = np.array([(x0 + (i % GRID_COLS) * GRID_PITCH, y0 + (i // GRID_COLS) * GRID_PITCH, 0.0) for i in range(N)])
        self.pos = self.grid_pos + np.array([0, 0, TAKEOFF_ALT])
        self.vel = np.zeros((N, 3))
        self.mission = [None] * N
        self.missions_done = []
        self.hist = {}          # frame -> 全機位置(LOG_STEP 刻み)
        self.sim_frame = sec(TAKEOFF_SEC)
        self.group_id = 0

    def set_mission(self, di, E, a, B, target):
        self.mission[di] = {"di": di, "S": self.pos[di].copy(), "E": np.array(E, float), "a": int(a), "B": int(B),
                            "target": target, "frames": [], "P": [], "done": None, "forced": False}

    def _active(self):
        return [i for i in range(N) if self.mission[i] is not None and self.mission[i]["done"] is None]

    def _step(self, f):
        dt = 1.0 / FPS
        act = self._active()
        if f % self.LOG_STEP == 0:
            self.hist[f] = self.pos.copy()
        if not act:
            return
        idx = np.array(act)
        M = [self.mission[i] for i in act]
        S = np.array([m["S"] for m in M])
        E = np.array([m["E"] for m in M])
        a = np.array([m["a"] for m in M], float)
        B = np.array([m["B"] for m in M], float)
        u = np.clip((f - a) / np.maximum(1.0, B - a), 0, 1)
        sm = 3 * u ** 2 - 2 * u ** 3
        ref = S + (E - S) * sm[:, None]
        p = self.pos[idx]
        v = self.vel[idx]
        acc = self.K_TRACK * (ref - p) - self.C_TRACK * v
        n = np.linalg.norm(acc, axis=1)
        acc *= np.minimum(1.0, self.A_TRACK / np.maximum(n, 1e-9))[:, None]
        # 反発(予測位置ベース)。自分の目標に近づいたら弱める(集合完成のため)
        pp_all = self.pos + self.vel * self.PREDICT
        pp = pp_all[idx]
        d = pp[:, None, :] - pp_all[None, :, :]
        dist = np.linalg.norm(d, axis=2)
        dist[np.arange(len(idx)), idx] = 1e9
        near = dist < self.R_REP
        if near.any():
            goal_d = np.linalg.norm(p - E, axis=1)
            gate_i = np.clip(goal_d / 3.0, 0.0, 1.0)
            # 自分が目標に近ければ(=ほぼ整列済み)反発を受けない。通過中の相手側が避ける。
            gate = np.broadcast_to(gate_i[:, None], dist.shape)
            hard = dist < 1.7
            gate = np.where(hard, 1.0, gate)
            mag = self.K_REP * (self.R_REP / np.maximum(dist, 0.3) - 1.0) * near * gate
            mag = np.minimum(mag, 12.0)
            dirv = d / np.maximum(dist, 1e-6)[:, :, None]
            perp = np.stack([-dirv[:, :, 1], dirv[:, :, 0], np.zeros_like(dirv[:, :, 0])], 2)
            acc += (mag[:, :, None] * (dirv + 0.35 * perp)).sum(1)
        n = np.linalg.norm(acc, axis=1)
        acc *= np.minimum(1.0, self.A_MAX / np.maximum(n, 1e-9))[:, None]
        v = v + acc * dt
        vxy = np.linalg.norm(v[:, :2], axis=1)
        v[:, :2] *= np.minimum(1.0, V_DESIGN["xy"] / np.maximum(vxy, 1e-9))[:, None]
        v[:, 2] = np.clip(v[:, 2], -V_DESIGN["down"], V_DESIGN["up"])
        p = p + v * dt
        self.pos[idx] = p
        self.vel[idx] = v
        for k, i in enumerate(act):
            m = self.mission[i]
            m["frames"].append(f)
            m["P"].append(p[k].copy())
            arrived = f >= m["B"] and np.linalg.norm(p[k] - m["E"]) < 0.06 and np.linalg.norm(v[k]) < 0.1
            timeout = f >= m["B"] + sec(12)
            if arrived or timeout:
                m["done"] = f
                m["forced"] = bool(timeout and not arrived)
                # 目標との残差を最後の2秒に分散(1フレームでのスナップを避ける)
                err = m["E"] - m["P"][-1]
                nb = min(len(m["P"]), sec(2))
                for q in range(nb):
                    w = (q + 1) / nb
                    m["P"][len(m["P"]) - nb + q] = m["P"][len(m["P"]) - nb + q] + err * w
                m["P"][-1] = m["E"].copy()
                self.pos[i] = m["E"].copy()
                self.vel[i] = 0.0
                self.missions_done.append(m)
                self.mission[i] = None

    def run_until(self, ids):
        """ids の全ミッションが完了するまで進める。返り値: 最後の完了フレーム"""
        ids = set(ids)
        last = self.sim_frame
        while True:
            self._step(self.sim_frame)
            self.sim_frame += 1
            pending = [i for i in ids if self.mission[i] is not None]
            if not pending:
                break
        last = max(m["done"] for m in self.missions_done if m["di"] in ids)
        return last

    def run_to(self, frame):
        while self.sim_frame < frame:
            self._step(self.sim_frame)
            self.sim_frame += 1

    def assign(self, drone_ids, cur_pos, tgt_pos):
        """二乗距離最小の割り当て(交差が減る)。返り値: {drone_id: target_index}"""
        cost = ((cur_pos[drone_ids][:, None, :] - tgt_pos[None, :, :]) ** 2).sum(2)
        a = hungarian(cost)
        return {di: int(ti) for di, ti in zip(drone_ids, a)}

    def move_all(self, formation, f_start):
        """全機を formation へ。返り値: 全機到着(整定)フレーム"""
        emp = formation["empties"]
        tgt = formation["rest_world"]
        ids = list(range(N))
        self.run_to(f_start)
        cur = self.pos.copy()
        amap = self.assign(ids, cur, tgt)
        T = transition_seconds(cur, tgt[[amap[i] for i in ids]])
        for di in ids:
            self.set_mission(di, tgt[amap[di]], f_start, f_start + sec(T), emp[amap[di]])
        f_end = self.run_until(ids) + 12
        formation["map"] = amap
        forced = sum(1 for m in self.missions_done if m["forced"])
        print(f"  move_all -> {formation['name']}: ref {T:.0f}s, arrived f{f_end} ({(f_end - f_start) / FPS:.1f}s) forced={forced}")
        return f_end

    def move_via_stars(self, star_formation, next_formation, f_out, star_hold_sec, star_color, alt_color=None):
        """暗転 → 星空間奏(N_STARS機点灯) → 次ページ。残りは消灯のまま直行。
        返り値: (f_star_in, f_star_out, f_next_in)"""
        emp_next = next_formation["empties"]
        tgt_next = next_formation["rest_world"]
        self.run_to(f_out)
        cur = self.pos.copy()
        ids = list(range(N))
        amap = self.assign(ids, cur, tgt_next)
        next_formation["map"] = amap
        order = np.argsort(self.lit_frames + nprng.random(N) * 0.01)   # 点灯の少ない機体を星に
        star_ids = [int(i) for i in order[:N_STARS]]
        other_ids = [i for i in ids if i not in set(star_ids)]
        emp_star = star_formation["empties"][:N_STARS]
        tgt_star = star_formation["rest_world"][:N_STARS]
        smap = self.assign(star_ids, cur, tgt_star)
        T1 = transition_seconds(cur[star_ids], tgt_star[[smap[i] for i in star_ids]])
        T2 = transition_seconds(tgt_star[[smap[i] for i in star_ids]], tgt_next[[amap[i] for i in star_ids]])
        T_oth = transition_seconds(cur[other_ids], tgt_next[[amap[i] for i in other_ids]])
        B_oth = f_out + sec(max(T_oth, T1 + 3 + star_hold_sec + T2))
        for di in star_ids:
            self.set_mission(di, tgt_star[smap[di]], f_out, f_out + sec(T1), emp_star[smap[di]])
        for di in other_ids:
            self.set_mission(di, tgt_next[amap[di]], f_out, B_oth, emp_next[amap[di]])
        f_star_in = self.run_until(star_ids) + 12
        f_star_out = f_star_in + sec(star_hold_sec)
        self.run_to(f_star_out)
        for di in star_ids:
            self.set_mission(di, tgt_next[amap[di]], f_star_out, f_star_out + sec(T2), emp_next[amap[di]])
        f_next_in = self.run_until(ids) + 12
        self.light_stars(star_ids, f_star_in, f_star_out, star_color, alt_color)
        star_formation["star_ids"] = star_ids
        forced = sum(1 for m in self.missions_done if m["forced"])
        print(f"  stars {star_formation['name']}: in f{f_star_in} out f{f_star_out}; next {next_formation['name']} in f{f_next_in} "
              f"(T1={T1:.0f}s hold={star_hold_sec}s T2={T2:.0f}s others={T_oth:.0f}s) forced={forced}")
        return f_star_in, f_star_out, f_next_in

    # ---------- 検証(シミュレーション結果)と書き込み ----------
    def check_conflicts(self, margin=1.8):
        frames = sorted(self.hist)
        pairs = {}
        for f in frames:
            P = self.hist[f]
            D = np.linalg.norm(P[:, None, :] - P[None, :, :], axis=2)
            ii, jj = np.where(np.triu(D < margin, 1))
            for i, j in zip(ii, jj):
                key = (int(i), int(j))
                d = float(D[i, j])
                if key not in pairs or d < pairs[key][0]:
                    pairs[key] = (d, f)
        self.unresolved = sorted([(round(v[0], 2), v[1], k[0] + 1, k[1] + 1) for k, v in pairs.items()])
        self.n_forced = sum(1 for m in self.missions_done if m["forced"])
        print(f"  sim pairs closer than {margin} m: {len(self.unresolved)}  (< {SAFE_DIST} m: "
              f"{sum(1 for u in self.unresolved if u[0] < SAFE_DIST)})  forced arrivals: {self.n_forced}")
        return self.unresolved

    def write_paths(self, key_step=6):
        """ミッションごとにパス・エンプティを焼き込み、機体のコンストレイントを乗り継がせる"""
        col = collection("Paths", collection("Formations"))
        n_keys = 0
        per_drone = [[] for _ in range(N)]
        for m in self.missions_done:
            per_drone[m["di"]].append(m)
        for di in range(N):
            d = self.drones[di]
            for k, m in enumerate(sorted(per_drone[di], key=lambda m: m["a"])):
                frames = m["frames"]
                P = np.array(m["P"])
                sel = list(range(0, len(frames), key_step))
                if sel[-1] != len(frames) - 1:
                    if len(frames) - 1 - sel[-1] < key_step // 2:
                        sel[-1] = len(frames) - 1
                    else:
                        sel.append(len(frames) - 1)
                e = new_empty(f"Drone {di + 1}.path.{k + 1:02d}", col, loc=tuple(P[0]), parent=self.oya_show, size=0.2)
                e.location = P[0]
                e.keyframe_insert("location", frame=frames[0])
                act = e.animation_data.action
                fcs = [fc for l in act.layers for st in l.strips for cb in st.channelbags for fc in cb.fcurves] if hasattr(act, "layers") else list(act.fcurves)
                fr = np.array([frames[i] for i in sel], float)
                for fc in fcs:
                    fc.keyframe_points.add(len(sel) - 1)
                    co = np.zeros(len(sel) * 2)
                    co[0::2] = fr
                    co[1::2] = P[sel, fc.array_index]
                    fc.keyframe_points.foreach_set("co", co)
                    fc.keyframe_points.foreach_set("interpolation", [2] * len(sel))
                    fc.keyframe_points.foreach_set("handle_left_type", [4] * len(sel))   # AUTO_CLAMPED
                    fc.keyframe_points.foreach_set("handle_right_type", [4] * len(sel))
                    fc.update()
                n_keys += 3 * len(sel)
                # 機体: パス → スロット
                self.con_count[di] += 1
                c1 = d.constraints.new("COPY_LOCATION")
                c1.name = f"T{self.con_count[di]:02d}.path[{e.name}]"
                c1.target = e
                c1.influence = 0.0
                d.keyframe_insert(f'constraints["{c1.name}"].influence', frame=frames[0] - 1)
                c1.influence = 1.0
                d.keyframe_insert(f'constraints["{c1.name}"].influence', frame=frames[0])
                self.con_count[di] += 1
                c2 = d.constraints.new("COPY_LOCATION")
                c2.name = f"T{self.con_count[di]:02d}.slot[{m['target'].name}]"
                c2.target = m["target"]
                c2.influence = 0.0
                d.keyframe_insert(f'constraints["{c2.name}"].influence', frame=m["done"] - 1)
                c2.influence = 1.0
                d.keyframe_insert(f'constraints["{c2.name}"].influence', frame=m["done"])
        # コンストレイントの influence キーは CONSTANT 補間(1フレームで切替・位置は連続)
        for d in self.drones:
            ad = d.animation_data
            if ad and ad.action:
                fcs = [fc for l in ad.action.layers for st in l.strips for cb in st.channelbags for fc in cb.fcurves] if hasattr(ad.action, "layers") else list(ad.action.fcurves)
                for fc in fcs:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "LINEAR"
        # 近接が残ったペアには Limit Distance(外側)でパッチ(プロの手法)
        patched = set()
        for dmin, f, i, j in getattr(self, "unresolved", []):
            if dmin >= SAFE_DIST or (j, i) in patched or (i, j) in patched:
                continue
            di, dj = i - 1, j - 1
            if any(c.type == "LIMIT_DISTANCE" and c.target == self.drones[di] for c in self.drones[dj].constraints):
                continue
            con = self.drones[di].constraints.new("LIMIT_DISTANCE")
            con.name = f"Keep away from Drone {j}"
            con.target = self.drones[dj]
            con.distance = SAFE_DIST + 0.1
            con.limit_mode = "LIMITDIST_OUTSIDE"
            patched.add((i, j))
        print(f"  baked {len(self.missions_done)} paths, {n_keys} keys; Limit Distance patches: {len(patched)}")
        self.n_path_keys = n_keys
        self.n_patches = len(patched)

    # ---------- LED ----------
    def key(self, di, frame, rgb, interp="CONSTANT"):
        self.led[di].append((int(frame), tuple(rgb), interp))

    def fade(self, di, f0, f1, rgb0, rgb1):
        self.key(di, f0, rgb0, "LINEAR")
        self.key(di, f1, rgb1, "CONSTANT")

    def mul(self, rgb, k):
        return (rgb[0] * k, rgb[1] * k, rgb[2] * k)

    def blackout(self, ids, f_end, dur=sec(1.5)):
        """f_end で完全消灯(dur フレームかけてフェード)。各機の現在色は直前キーから取る"""
        for di in ids:
            cur = self.led[di][-1][1] if self.led[di] else BLACK
            self.fade(di, f_end - dur, f_end, cur, BLACK)

    def light_stars(self, ids, f_in, f_out, color, alt_color=None):
        r = random.Random(f_in)
        for di in ids:
            c = color if (alt_color is None or r.random() < 0.7) else alt_color
            f = f_in + int(r.random() * sec(5))     # じわ見せ: 5秒かけてランダム点灯
            self.fade(di, f, f + sec(0.6), BLACK, c)
            t = f + sec(0.6)
            while t + sec(1.6) < f_out - sec(1.5):
                t += sec(r.uniform(0.8, 2.4))
                dim = self.mul(c, r.uniform(0.15, 0.4))
                self.key(di, t, c, "LINEAR")
                self.key(di, t + sec(0.35), dim, "LINEAR")
                self.key(di, t + sec(0.8), c, "CONSTANT")
            self.fade(di, f_out - sec(1.5), f_out, c, BLACK)
            self.lit_frames[di] += (f_out - f)

    def formation_ids(self, formation, part=None):
        amap = formation["map"]
        inv = {ti: di for di, ti in amap.items()}
        out = []
        for ti, e in enumerate(formation["empties"]):
            if formation["part"][ti] == "park":
                continue
            if part is not None and formation["part"][ti] != part:
                continue
            out.append((inv[ti], ti))
        return out

    # ---------- 書き出し ----------
    def write_led_keys(self):
        interp_id = {"CONSTANT": 0, "LINEAR": 1, "BEZIER": 2}
        for di in range(N):
            keys = sorted(self.led[di], key=lambda k: k[0])
            # 同一フレームの重複は後勝ち
            dedup = {}
            for f, c, it in keys:
                dedup[f] = (c, it)
            frames = sorted(dedup)
            mat = self.mats[di]
            em = mat.node_tree.nodes["Emission"]
            em.inputs[0].default_value = (*dedup[frames[0]][0], 1.0)
            em.inputs[0].keyframe_insert("default_value", frame=frames[0])
            act = mat.node_tree.animation_data.action
            fcs = []
            if hasattr(act, "layers"):
                for layer in act.layers:
                    for strip in layer.strips:
                        for cb in strip.channelbags:
                            fcs.extend(cb.fcurves)
            else:
                fcs = list(act.fcurves)
            nk = len(frames)
            for fc in fcs:
                idx = fc.array_index
                if idx > 2:
                    continue
                fc.keyframe_points.add(nk - 1)
                co = np.zeros(nk * 2)
                co[0::2] = frames
                co[1::2] = [dedup[f][0][idx] for f in frames]
                fc.keyframe_points.foreach_set("co", co)
                fc.keyframe_points.foreach_set("interpolation", [interp_id[dedup[f][1]] for f in frames])
                fc.update()

    def write_markers(self):
        scene = bpy.context.scene
        for name, f in self.markers:
            scene.timeline_markers.new(name, frame=f)


HEAD_PIVOT = (0.0, 0.0, 0.0)


def skull_pivots(parts, jaw_pivot):
    """頭部(霧以外)は HEAD_PIVOT の子、顎は頭部ピボットの子(首振りに追従して開閉)"""
    pv = {}
    for part in parts:
        if part == "mist":
            continue
        if part in ("jaw", "lower_teeth"):
            pv[part] = (jaw_pivot, "cranium")
        else:
            pv[part] = (HEAD_PIVOT, None)
    return pv


# =============================== 30秒版: スカル本編 ===============================
def page_skull_30s(sb, F_skull, f_in, jaw_pivot):
    """本編30秒: 0-4s 上→下スキャン点灯 / 4.5s 目が赤く脈動 / 5-11s 左へ25° / 11-19s 右へ-25° /
    19-25s 正面へ / 22-28s 顎を開閉(目が白く光る) / 28.5-30s 消灯。紫の霧は終始ゆっくり明滅"""
    f_out = f_in + sec(CONTENT_SEC)
    r = random.Random(4)
    tgt = F_skull["rest_world"]
    ztop, zbot = tgt[:, 2].max(), tgt[:, 2].min()
    for di, ti in sb.formation_ids(F_skull):
        part = F_skull["part"][ti]
        col = F_skull["colors"][ti]
        if part == "eyes":
            continue
        if part == "mist":
            t = f_in + int(r.random() * sec(2))
            while t < f_out - sec(3):
                sb.key(di, t, sb.mul(COL["mist"], 0.15), "LINEAR")
                sb.key(di, t + sec(1.2), COL["mist"], "LINEAR")
                sb.key(di, t + sec(2.4), sb.mul(COL["mist"], 0.15), "CONSTANT")
                t += sec(r.uniform(2.6, 4.5))
            sb.lit_frames[di] += (f_out - f_in) * 0.5
            continue
        ff = f_in + int((ztop - tgt[ti][2]) / (ztop - zbot) * sec(4))
        sb.key(di, ff, col, "CONSTANT")
        sb.lit_frames[di] += f_out - ff
    eye_ids = sb.formation_ids(F_skull, "eyes")
    f_eye = f_in + sec(4.5)
    for di, ti in eye_ids:
        sb.key(di, f_eye, COL["red"], "LINEAR")
        t = f_eye
        while t < f_out - sec(2):
            t += 8
            ph = (t - f_eye) / sec(1.6) * 2 * math.pi
            sb.key(di, t, sb.mul(COL["red"], 0.55 + 0.45 * math.sin(ph)), "LINEAR")
        sb.key(di, f_in + sec(24.0), (1.0, 0.6, 0.5), "LINEAR")   # 顎が開き切るところで白く
        sb.key(di, f_in + sec(26.0), COL["red"], "LINEAR")
        sb.lit_frames[di] += f_out - f_eye
    sb.blackout(range(N), f_out, dur=sec(1.5))
    # 首振り: 頭部ピボットの Z 回転(霧は回さない。半径約17.5m → ピーク約2.9m/s)
    head = F_skull["pivots"][HEAD_PIVOT]
    head.rotation_mode = "XYZ"
    for t_s, ang in ((5, 0), (11, 25), (19, -25), (25, 0)):
        head.rotation_euler[2] = math.radians(ang)
        head.keyframe_insert("rotation_euler", index=2, frame=f_in + sec(t_s))
    sb.marker("スカル.首振り", f_in + sec(5))
    # 顎: 11°を3秒で開き、0.6秒保持、3秒で閉じる
    jaw = F_skull["pivots"][jaw_pivot]
    jaw.rotation_mode = "XYZ"
    for t_s, ang in ((22, 0), (25, 11), (25.6, 11), (28, 0)):
        jaw.rotation_euler[0] = math.radians(ang)
        jaw.keyframe_insert("rotation_euler", index=0, frame=f_in + sec(t_s))
    sb.marker("スカル.顎開閉", f_in + sec(22))
    sb.pages.append(("01 スカル(3D・スキャン点灯・首振り・顎開閉・目の脈動・紫の霧)", f_in, f_out, F_skull["n_lit"]))
    return f_out


# =============================== ショー本体 ===============================
def build_show():
    t0 = time.time()
    clear_scene()
    scene = setup_scene(20000)
    sb = ShowBuilder()
    sb.build_base()
    sb._init_plan()
    add_flight_area()
    setup_cameras(scene, sb.oya_show)

    JAW_PIVOT = (0.0, 1.0 * SKULL_SCALE, -7.0 * SKULL_SCALE)
    if SHOW_MODE == "30s":
        # ---------------- 30秒版: 離陸(消灯) → 遷移(消灯) → スカル30秒 → 帰投(消灯) → 着陸 ----------------
        print("formations:")
        skull_parts, jaw_parts = make_skull()
        allskull = dict(skull_parts)
        allskull.update(jaw_parts)
        F_skull = sb.add_formation("01_Skull", allskull, pivots=skull_pivots(allskull, JAW_PIVOT))
        f = sb.frame
        sb.marker("遷移(消灯)", f)
        f_sk_in = sb.move_all(F_skull, f)
        sb.marker("本編開始 スカル(30秒)", f_sk_in)
        f_sk_out = page_skull_30s(sb, F_skull, f_sk_in, JAW_PIVOT)
        sb.marker("本編終了", f_sk_out)
        sb.marker("帰投(消灯)", f_sk_out)
        grid_f = {"name": "Takeoff grid", "empties": sb.grid, "part": ["grid"] * N,
                  "rest_world": sb.grid_pos + np.array([0, 0, TAKEOFF_ALT])}
        f_land_in = sb.move_all(grid_f, f_sk_out + sec(1))
        sb.marker("降下・着陸", f_land_in)
        sb.oya_takeoff.location = (0, 0, TAKEOFF_ALT)
        sb.oya_takeoff.keyframe_insert("location", frame=f_land_in)
        sb.oya_takeoff.location = (0, 0, 0)
        f_end = f_land_in + sec(20)
        sb.oya_takeoff.keyframe_insert("location", frame=f_end)
        sb.marker("着陸完了", f_end)
        scene.frame_end = f_end
        scene.use_preview_range = True          # 再生範囲=本編30秒
        scene.frame_preview_start = f_sk_in
        scene.frame_preview_end = f_sk_out
        for i in range(N):
            sb.key(i, f_end, BLACK, "CONSTANT")
        text_spacing = 0.0
        content = (f_sk_in, f_sk_out)
        return finish_show(sb, scene, f_land_in, f_end, text_spacing, content)

    # ---------------- 長尺版(full): フォーメーションを先に全部作る ----------------
    print("formations:")
    F_stars1 = sb.add_formation("01_Stars.purple", {"stars": (make_stars(N_STARS, SEED + 1), COL["purple"])})
    pumpkin_parts = make_pumpkin()
    F_pumpkin = sb.add_formation("02_Pumpkin", pumpkin_parts)
    F_stars2 = sb.add_formation("03_Stars.green", {"stars": (make_stars(N_STARS, SEED + 2), COL["green"])})
    skull_parts, jaw_parts = make_skull()
    allskull = dict(skull_parts)
    allskull.update(jaw_parts)
    F_skull = sb.add_formation("04_Skull", allskull, pivots=skull_pivots(allskull, JAW_PIVOT))
    bat_fixed, bat_wings = make_bat()
    allbat = dict(bat_fixed)
    allbat.update(bat_wings)
    F_bat = sb.add_formation("05_Bat", allbat,
                             pivots={"wingR": ((4.0, 0.0, 8.0), None), "wingL": ((-4.0, 0.0, 8.0), None)})
    F_stars3 = sb.add_formation("06_Stars.orange", {"stars": (make_stars(N_STARS, SEED + 3), COL["orange"])})
    text_parts, letter_ids, text_spacing = make_text()
    F_text = sb.add_formation("07_Text.HAPPY_HALLOWEEN", text_parts)
    print(f"  text spacing {text_spacing:.2f} m, {len(text_parts['text'][0])} drones on strokes")

    # ---------------- タイムライン ----------------
    f = sb.frame                                            # 離陸完了 = 360
    # 1) 冒頭: 消灯のまま星空へ(星は 90 機だけ、残りはかぼちゃへ直行)
    f_s1_in, f_s1_out, f_pk_in = sb.move_via_stars(F_stars1, F_pumpkin, f, 20, COL["purple"], COL["orange"])
    sb.marker("大遷移(消灯)", f)
    sb.marker("01 星空・紫", f_s1_in)
    sb.pages.append(("01 星空(紫/橙トゥインクル)", f_s1_in, f_s1_out, N_STARS))

    # 2) かぼちゃ 28秒: ランダム点灯 3秒 → 顔が一発点灯 → ろうそくの揺らぎ → 左右に揺れる
    f_pk_out = f_pk_in + sec(28)
    sb.marker("02 ジャック・オー・ランタン", f_pk_in)
    r = random.Random(11)
    for di, ti in sb.formation_ids(F_pumpkin, "body"):
        ff = f_pk_in + int(r.random() * sec(3))
        sb.fade(di, ff, ff + sec(0.5), BLACK, COL["pumpkin"])
        sb.lit_frames[di] += f_pk_out - ff
    for di, ti in sb.formation_ids(F_pumpkin, "stem"):
        sb.fade(di, f_pk_in + sec(3), f_pk_in + sec(3.5), BLACK, COL["stem"])
        sb.lit_frames[di] += f_pk_out - f_pk_in
    for di, ti in sb.formation_ids(F_pumpkin, "face"):
        f_face = f_pk_in + sec(4.0)
        sb.key(di, f_face, COL["candle"], "CONSTANT")            # 一発点灯
        t = f_face + sec(1.0)
        while t < f_pk_out - sec(2):
            k = r.uniform(0.55, 1.0)
            sb.key(di, t, sb.mul(COL["candle"], k), "LINEAR")
            t += 4
        sb.lit_frames[di] += f_pk_out - f_face
    sb.blackout(range(N), f_pk_out)
    # 揺れ: 親の Z 回転 ±10°(周期 12 秒)。外周半径16m → ピーク約1.4m/s
    root = F_pumpkin["root"]
    root.rotation_mode = "XYZ"
    t = f_pk_in + sec(5)
    k = 0
    while t <= f_pk_out - sec(4):
        root.rotation_euler[2] = math.radians([0, 10, 0, -10][k % 4])
        root.keyframe_insert("rotation_euler", index=2, frame=t)
        t += sec(3.0)
        k += 1
    root.rotation_euler[2] = 0
    root.keyframe_insert("rotation_euler", index=2, frame=f_pk_out)

    # 3) 星空・緑 → スカルへ
    f_s2_in, f_s2_out, f_sk_in = sb.move_via_stars(F_stars2, F_skull, f_pk_out, 20, COL["green"], COL["purple"])
    sb.marker("03 星空・緑", f_s2_in)
    sb.pages.append(("02 ジャック・オー・ランタン(3D・揺れ・ろうそく)", f_pk_in, f_pk_out, F_pumpkin["n_lit"]))
    sb.pages.append(("03 星空(緑/紫)", f_s2_in, f_s2_out, N_STARS))

    # 4) スカル 80秒: 上から下へスキャン点灯 6秒 → 目が赤く脈動 → 360°回転 56秒 → 顎を2回開閉 → 消灯
    f_sk_out = f_sk_in + sec(80)
    sb.marker("04 スカル(3D)", f_sk_in)
    tgt = F_skull["rest_world"]
    ztop, zbot = tgt[:, 2].max(), tgt[:, 2].min()
    for di, ti in sb.formation_ids(F_skull):
        part = F_skull["part"][ti]
        col = F_skull["colors"][ti]
        if part == "eyes":
            continue
        if part == "mist":
            t = f_sk_in + sec(2) + int(r.random() * sec(4))
            while t < f_sk_out - sec(4):
                sb.key(di, t, sb.mul(COL["mist"], 0.15), "LINEAR")
                sb.key(di, t + sec(1.5), COL["mist"], "LINEAR")
                sb.key(di, t + sec(3.0), sb.mul(COL["mist"], 0.15), "CONSTANT")
                t += sec(r.uniform(3.5, 7.0))
            sb.lit_frames[di] += (f_sk_out - f_sk_in) * 0.5
            continue
        ff = f_sk_in + int((ztop - tgt[ti][2]) / (ztop - zbot) * sec(6))
        sb.key(di, ff, col, "CONSTANT")
        sb.lit_frames[di] += f_sk_out - ff
    sb.marker("スカル.回転開始", f_sk_in + sec(9))
    sb.marker("スカル.顎開閉", f_sk_in + sec(66))
    eye_ids = sb.formation_ids(F_skull, "eyes")
    f_eye = f_sk_in + sec(6.5)
    for di, ti in eye_ids:
        sb.key(di, f_eye, COL["red"], "LINEAR")
        t = f_eye
        while t < f_sk_out - sec(2):
            t += 12
            ph = (t - f_eye) / sec(2.0) * 2 * math.pi
            k = 0.55 + 0.45 * math.sin(ph)
            sb.key(di, t, sb.mul(COL["red"], k), "LINEAR")
        sb.lit_frames[di] += f_sk_out - f_eye
    # 顎の開閉に合わせて目を白く光らせる
    for chomp in (f_sk_in + sec(66), f_sk_in + sec(72)):
        for di, ti in eye_ids:
            sb.key(di, chomp + sec(2.0), (1.0, 0.6, 0.5), "LINEAR")
            sb.key(di, chomp + sec(4.0), COL["red"], "LINEAR")
    sb.blackout(range(N), f_sk_out, dur=sec(2))
    root = F_skull["pivots"][HEAD_PIVOT]
    root.rotation_mode = "XYZ"
    root.rotation_euler[2] = 0
    root.keyframe_insert("rotation_euler", index=2, frame=f_sk_in + sec(9))
    root.rotation_euler[2] = math.radians(360)
    root.keyframe_insert("rotation_euler", index=2, frame=f_sk_in + sec(65))
    jaw = F_skull["pivots"][JAW_PIVOT]
    jaw.rotation_mode = "XYZ"
    # 顎先は支点から約16m → 11°を3秒で(ピーク約1.5m/s・加速度約2m/s²)
    for chomp in (f_sk_in + sec(66), f_sk_in + sec(72)):
        for off, ang in ((0, 0), (sec(3.0), 11), (sec(3.6), 11), (sec(6.0), 0)):
            jaw.rotation_euler[0] = math.radians(ang)
            jaw.keyframe_insert("rotation_euler", index=0, frame=chomp + off)

    # 5) 暗転を長めに(タメ 3秒)→ コウモリ(消灯移動)
    f_bt_in = sb.move_all(F_bat, f_sk_out + sec(1))
    f_bt_out = f_bt_in + sec(26)
    sb.marker("05 コウモリ", f_bt_in)
    sb.pages.append(("04 スカル(3D・スキャン点灯・360°回転・顎開閉・目の脈動・紫の霧)", f_sk_in, f_sk_out, F_skull["n_lit"]))
    for di, ti in sb.formation_ids(F_bat):
        part = F_bat["part"][ti]
        col = F_bat["colors"][ti]
        if part == "eyes":
            sb.key(di, f_bt_in + sec(1.5), COL["red"], "CONSTANT")
            for blink in (8, 15, 21):
                sb.key(di, f_bt_in + sec(blink), BLACK, "CONSTANT")
                sb.key(di, f_bt_in + sec(blink + 0.3), COL["red"], "CONSTANT")
            sb.lit_frames[di] += f_bt_out - f_bt_in
            continue
        sb.key(di, f_bt_in, col, "CONSTANT")                 # 一発点灯
        sb.lit_frames[di] += f_bt_out - f_bt_in
    # 翼の縁を明滅(シアン)で走らせる: 翼パーツを 3 秒周期で青→シアン→青
    for di, ti in sb.formation_ids(F_bat):
        if F_bat["part"][ti] in ("wingL", "wingR"):
            t = f_bt_in + sec(4)
            while t < f_bt_out - sec(3):
                sb.key(di, t, COL["blue"], "LINEAR")
                sb.key(di, t + sec(1.5), COL["cyan"], "LINEAR")
                sb.key(di, t + sec(3.0), COL["blue"], "CONSTANT")
                t += sec(6)
    sb.blackout(range(N), f_bt_out)
    # 羽ばたき: 翼ピボットを Y 軸回りに ±6°(周期 10 秒)
    for key, sgn in (((4.0, 0.0, 8.0), -1), ((-4.0, 0.0, 8.0), 1)):
        pv = F_bat["pivots"][key]
        pv.rotation_mode = "XYZ"
        t = f_bt_in + sec(1)
        k = 0
        while t <= f_bt_out - sec(2):
            pv.rotation_euler[1] = math.radians(sgn * [0, 6, 0, -6][k % 4])
            pv.keyframe_insert("rotation_euler", index=1, frame=t)
            t += sec(2.5)
            k += 1
        pv.rotation_euler[1] = 0
        pv.keyframe_insert("rotation_euler", index=1, frame=f_bt_out)

    # 6) 星空・橙 → 文字へ
    f_s3_in, f_s3_out, f_tx_in = sb.move_via_stars(F_stars3, F_text, f_bt_out, 16, COL["orange"], COL["purple"])
    sb.marker("06 星空・橙", f_s3_in)
    sb.pages.append(("05 コウモリ(羽ばたき・目の明滅)", f_bt_in, f_bt_out, F_bat["n_lit"]))
    sb.pages.append(("06 星空(橙/紫)", f_s3_in, f_s3_out, N_STARS))

    # 7) 文字 26秒: 1文字ずつ白で点灯(タイプライター)→ 橙へ変色 → スパークル → 消灯
    f_tx_out = f_tx_in + sec(26)
    sb.marker("07 HAPPY HALLOWEEN", f_tx_in)
    uniq = sorted(set(letter_ids))
    for di, ti in sb.formation_ids(F_text, "text"):
        lid = letter_ids[ti]
        ff = f_tx_in + sec(0.7) * uniq.index(lid)
        sb.key(di, ff, COL["white"], "CONSTANT")
        sb.key(di, f_tx_in + sec(15), COL["white"], "LINEAR")
        sb.key(di, f_tx_in + sec(17), COL["amber"], "CONSTANT")
        sb.lit_frames[di] += f_tx_out - ff
    r = random.Random(77)
    for di, ti in sb.formation_ids(F_text, "sparkle"):
        t = f_tx_in + sec(2) + int(r.random() * sec(2))
        while t < f_tx_out - sec(3):
            sb.key(di, t, BLACK, "LINEAR")
            sb.key(di, t + sec(0.3), COL["amber"], "LINEAR")
            sb.key(di, t + sec(0.7), BLACK, "CONSTANT")
            t += sec(r.uniform(1.0, 3.0))
        sb.lit_frames[di] += (f_tx_out - f_tx_in) * 0.3
    sb.blackout(range(N), f_tx_out, dur=sec(2))
    sb.pages.append(("07 HAPPY HALLOWEEN(タイプライター→橙→スパークル)", f_tx_in, f_tx_out, F_text["n_lit"]))

    # 8) 帰投(消灯)→ 着陸グリッド(離陸グリッドを再利用)→ 降下 20 秒
    sb.marker("帰投(消灯)", f_tx_out)
    grid_f = {"name": "Takeoff grid", "empties": sb.grid, "part": ["grid"] * N,
              "rest_world": sb.grid_pos + np.array([0, 0, TAKEOFF_ALT])}
    f_land_in = sb.move_all(grid_f, f_tx_out + sec(1))
    sb.marker("降下・着陸", f_land_in)
    sb.oya_takeoff.location = (0, 0, TAKEOFF_ALT)
    sb.oya_takeoff.keyframe_insert("location", frame=f_land_in)
    sb.oya_takeoff.location = (0, 0, 0)
    f_end = f_land_in + sec(20)
    sb.oya_takeoff.keyframe_insert("location", frame=f_end)
    sb.marker("着陸完了", f_end)
    scene.frame_end = f_end
    for i in range(N):
        sb.key(i, f_end, BLACK, "CONSTANT")

    content = (sb.pages[0][1], sb.pages[-1][2])
    return finish_show(sb, scene, f_land_in, f_end, text_spacing, content)


def finish_show(sb, scene, f_land_in, f_end, text_spacing, content):
    t0 = time.time()
    # ---------------- 検証 → 書き出し ----------------
    sb.run_to(f_land_in)
    sb.check_conflicts()
    sb.write_paths()
    print("writing LED keys ...")
    sb.write_led_keys()
    sb.write_markers()
    # 離陸親の補間を滑らかに(既定ベジエ)。ショー親は原点(会場合わせはここで)
    sb.oya_show.location = (0, 0, 0)

    # 尺割り表
    plan = {
        "show": SHOW_NAME, "mode": SHOW_MODE, "fps": FPS, "drones": N, "frame_end": f_end,
        "content_frames": [content[0], content[1]], "content_sec": round((content[1] - content[0]) / FPS, 1),
        "duration_sec": round(f_end / FPS, 1),
        "pages": [{"page": p, "frame_in": a, "frame_out": b, "sec_in": round(a / FPS, 1), "sec_out": round(b / FPS, 1),
                   "duration": round((b - a) / FPS, 1), "lit_drones": n} for p, a, b, n in sb.pages],
        "markers": [{"name": n, "frame": fr, "sec": round(fr / FPS, 1)} for n, fr in sb.markers],
        "formations": {k: {"n_lit": v["n_lit"], "min_spacing_m": round(v["min_dist"], 2)} for k, v in sb.formations.items()},
        "lit_ratio_per_drone": {"min": round(float(sb.lit_frames.min() / f_end), 3),
                                "max": round(float(sb.lit_frames.max() / f_end), 3),
                                "mean": round(float(sb.lit_frames.mean() / f_end), 3)},
        "text_spacing_m": round(text_spacing, 2),
        "transition_sim": {"pairs_closer_than_1.8m": len(sb.unresolved), "closest_pairs": sb.unresolved[:40],
                           "forced_arrivals": sb.n_forced, "path_keys": sb.n_path_keys, "limit_distance_patches": sb.n_patches},
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "show_plan.json"), "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=2)

    # テキストデータブロックに道具を同梱
    try:
        src = open(os.path.join(HERE, "build_halloween_skull_show.py"), encoding="utf-8").read()
        bpy.data.texts.new("build_halloween_skull_show.py").from_string(src)
    except Exception as ex:
        print("embed build script skipped:", ex)
    for extra in ("verify_and_preview.py",):
        p = os.path.join(HERE, extra)
        if os.path.exists(p):
            bpy.data.texts.new(extra).from_string(open(p, encoding="utf-8").read())
    bpy.data.texts.new("show_plan.json").from_string(json.dumps(plan, ensure_ascii=False, indent=2))

    # 孤立データ掃除
    for blk in (bpy.data.actions, bpy.data.materials, bpy.data.meshes):
        for x in list(blk):
            if x.users == 0:
                blk.remove(x)

    if os.environ.get("SHOW_SKIP_SAVE") != "1":
        path = os.path.join(OUT_DIR, SHOW_NAME + ".blend")
        bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
        print("saved:", path)
    print(f"done ({time.time() - t0:.1f}s in finish)  total {f_end} frames = {f_end / FPS:.1f}s  content {plan['content_sec']}s")
    return plan


if __name__ == "__main__":
    build_show()
