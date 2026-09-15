# -*- coding: utf-8 -*-
"""
ショー検証 + プレビュー書き出し(Blender内実行)
  - 安全チェック: 水平/上昇/下降速度・加速度・最小機体間距離(全編・全機)
  - ギャラリー: 各ページ中間フレームの正面ビューSVG + Cyclesレンダー(PNG)
使い方
  blender -b 20261031_Halloween_SKULL_Animation_v01.blend -P verify_and_preview.py
  python verify_and_preview.py   (pip版bpy: 同じフォルダの .blend を開く)
環境変数
  SHOW_RENDER=0   レンダーを省略(安全チェックのみ)
  SHOW_SAMPLES=16 Cyclesサンプル数
  SHOW_VIDEO=1    全編プレビュー動画用の連番PNGも書き出す(6fps・640x480)
"""
import bpy
import os
import sys
import json
import math
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
BLEND = os.path.join(HERE, "20261031_Halloween_SKULL_Animation_v01.blend")
OUT = os.path.join(HERE, "previews")
FPS = 24
LIMITS = {"vel_xy": 5.0, "vel_up": 4.0, "vel_down": 3.0, "accel": 4.0, "min_dist": 1.5}
DESIGN = {"vel_xy": 3.0, "vel_up": 2.4, "vel_down": 1.8, "accel": 2.4, "min_dist": 1.5}


def drones():
    out = []
    i = 1
    while True:
        o = bpy.data.objects.get(f"Drone {i}")
        if not o:
            break
        out.append(o)
        i += 1
    return out


def sample_positions(objs, f0, f1, step):
    frames = list(range(f0, f1 + 1, step))
    P = np.zeros((len(frames), len(objs), 3))
    sc = bpy.context.scene
    for k, f in enumerate(frames):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        for i, o in enumerate(objs):
            P[k, i] = o.evaluated_get(dg).matrix_world.translation[:]
    return np.array(frames), P


def safety(frames, P):
    dt = (frames[1] - frames[0]) / FPS
    V = np.diff(P, axis=0) / dt                      # (F-1, N, 3)
    A = np.diff(V, axis=0) / dt                      # (F-2, N, 3)
    vxy = np.linalg.norm(V[:, :, :2], axis=2)
    vz = V[:, :, 2]
    amag = np.linalg.norm(A, axis=2)
    rep = {
        "max_vel_xy": float(vxy.max()), "max_vel_up": float(vz.max()), "max_vel_down": float(-vz.min()),
        "max_accel": float(amag.max()),
    }
    # 最小距離(全フレーム・全ペア)
    mind = np.full(len(frames), 1e9)
    minpair = [None] * len(frames)
    for k in range(len(frames)):
        D = np.linalg.norm(P[k][:, None, :] - P[k][None, :, :], axis=2)
        np.fill_diagonal(D, 1e9)
        idx = int(np.argmin(D))
        i, j = divmod(idx, D.shape[1])
        mind[k] = D[i, j]
        minpair[k] = (i + 1, j + 1)
    kmin = int(np.argmin(mind))
    rep["min_dist"] = float(mind[kmin])
    rep["min_dist_frame"] = int(frames[kmin])
    rep["min_dist_pair"] = minpair[kmin]
    air = (frames > 24 * 20) & (frames < frames[-1] - 24 * 25)   # 離陸完了〜降下開始
    rep["altitude_min_airborne"] = float(P[air][:, :, 2].min()) if air.any() else None
    rep["altitude_max"] = float(P[:, :, 2].max())
    viol = []
    for k in range(len(frames) - 1):
        f = int(frames[k])
        bad = np.where((vxy[k] > LIMITS["vel_xy"]) | (vz[k] > LIMITS["vel_up"]) | (-vz[k] > LIMITS["vel_down"]))[0]
        for i in bad[:5]:
            viol.append({"frame": f, "drone": int(i + 1), "type": "velocity",
                         "value": round(float(max(vxy[k, i], abs(vz[k, i]))), 2)})
        if k < len(A):
            bad = np.where(amag[k] > LIMITS["accel"])[0]
            for i in bad[:5]:
                viol.append({"frame": f, "drone": int(i + 1), "type": "accel", "value": round(float(amag[k, i]), 2)})
        if mind[k] < LIMITS["min_dist"]:
            viol.append({"frame": f, "drone": f"{minpair[k][0]}-{minpair[k][1]}", "type": "proximity",
                         "value": round(float(mind[k]), 2)})
    rep["n_violations"] = len(viol)
    rep["violations"] = viol[:200]
    # 区間ごとの最大速度(マーカー区間)
    sc = bpy.context.scene
    marks = sorted([(m.frame, m.name) for m in sc.timeline_markers])
    seg = []
    for a, b in zip(marks, marks[1:] + [(int(frames[-1]) + 1, "end")]):
        m = (frames[:-1] >= a[0]) & (frames[:-1] < b[0])
        if not m.any():
            continue
        seg.append({"from": a[1], "frame": a[0], "sec": round(a[0] / FPS, 1),
                    "max_vel_xy": round(float(vxy[m].max()), 2),
                    "max_vel_up": round(float(vz[m].max()), 2),
                    "max_vel_down": round(float(-vz[m].min()), 2),
                    "max_accel": round(float(amag[m[:len(amag)]].max()), 2) if m[:len(amag)].any() else None,
                    "min_dist": round(float(mind[:-1][m].min()), 2)})
    rep["segments"] = seg
    return rep, mind


def _fcurves(action):
    if hasattr(action, "layers"):
        return [fc for l in action.layers for s in l.strips for cb in s.channelbags for fc in cb.fcurves]
    return list(action.fcurves)


def led_colors(objs, frame):
    out = np.zeros((len(objs), 3))
    for i, o in enumerate(objs):
        mat = o.data.materials[0]
        ad = mat.node_tree.animation_data
        if ad and ad.action:
            for fc in _fcurves(ad.action):
                if fc.data_path.endswith("default_value") and fc.array_index < 3:
                    out[i, fc.array_index] = fc.evaluate(frame)
        else:
            em = next(n for n in mat.node_tree.nodes if n.type == "EMISSION")
            out[i] = em.inputs[0].default_value[:3]
    return out


def gallery_svg(objs, frames_labels, path, canvas=(-75, 75, 20, 120)):
    x0, x1, z0, z1 = canvas
    W, H = 420, 280
    cols = min(4, len(frames_labels))
    rows = math.ceil(len(frames_labels) / cols)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{cols * W}" height="{rows * H}" style="background:#000">']
    sc = bpy.context.scene
    for idx, (f, label) in enumerate(frames_labels):
        ox, oy = (idx % cols) * W, (idx // cols) * H
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        pts = [o.evaluated_get(dg).matrix_world.translation[:] for o in objs]
        cols_ = led_colors(objs, f)
        parts.append(f'<rect x="{ox}" y="{oy}" width="{W}" height="{H}" fill="#050308" stroke="#222"/>')
        parts.append(f'<text x="{ox + 8}" y="{oy + 16}" fill="#999" font-size="12" font-family="sans-serif">'
                     f'f{f} ({f / FPS:.1f}s) {label}</text>')
        for p, c in zip(pts, cols_):
            px = ox + (p[0] - x0) / (x1 - x0) * W
            pz = oy + H - (p[2] - z0) / (z1 - z0) * H
            if c.max() > 0.05:
                cc = f"rgb({int(min(1, c[0]) * 255)},{int(min(1, c[1]) * 255)},{int(min(1, c[2]) * 255)})"
                parts.append(f'<circle cx="{px:.1f}" cy="{pz:.1f}" r="2.4" fill="{cc}"/>')
            else:
                parts.append(f'<circle cx="{px:.1f}" cy="{pz:.1f}" r="0.9" fill="#2a2a2a"/>')
    parts.append("</svg>")
    with open(path, "w") as fh:
        fh.write("".join(parts))


def render_frames(frames_labels, samples=16, res=(1200, 900), cam="AudienceCam", prefix="page"):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.cycles.device = "CPU"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.use_compositing = True
    sc.camera = bpy.data.objects[cam]
    out = []
    for f, label in frames_labels:
        sc.frame_set(f)
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label)
        path = os.path.join(OUT, f"{prefix}_{f:05d}_{safe}.png")
        sc.render.filepath = path
        t = time.time()
        bpy.ops.render.render(write_still=True)
        print(f"  rendered {os.path.basename(path)} ({time.time() - t:.1f}s)")
        out.append(path)
    return out


def main():
    if bpy.data.filepath == "" and os.path.exists(BLEND):
        bpy.ops.wm.open_mainfile(filepath=BLEND)
    os.makedirs(OUT, exist_ok=True)
    sc = bpy.context.scene
    objs = drones()
    plan = json.loads(bpy.data.texts["show_plan.json"].as_string()) if "show_plan.json" in bpy.data.texts else None
    t0 = time.time()
    print(f"sampling {len(objs)} drones, frames 0..{sc.frame_end} ...")
    frames, P = sample_positions(objs, 0, sc.frame_end, 3)     # 0.125秒刻み
    print(f"  sampled in {time.time() - t0:.1f}s")
    rep, mind = safety(frames, P)
    rep["limits"] = LIMITS
    rep["design_targets"] = DESIGN
    rep["sample_step_sec"] = 3 / FPS
    rep["n_drones"] = len(objs)
    rep["frames"] = int(sc.frame_end)
    rep["duration_sec"] = round(sc.frame_end / FPS, 1)
    with open(os.path.join(HERE, "safety_report.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=2)
    print("SAFETY:", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in rep.items()
                      if k in ("max_vel_xy", "max_vel_up", "max_vel_down", "max_accel", "min_dist", "min_dist_frame",
                               "min_dist_pair", "n_violations", "altitude_min_airborne", "altitude_max")})
    # 点灯機数の推移(色の健全性)
    lit = []
    for f in range(0, sc.frame_end + 1, 24):
        c = led_colors(objs, f)
        lit.append((f, int((c.max(1) > 0.05).sum())))
    with open(os.path.join(HERE, "lit_count_per_sec.json"), "w") as fh:
        json.dump(lit, fh)

    # ---- ギャラリー ----
    gal = []
    if plan:
        for pg in plan["pages"]:
            a, b = pg["frame_in"], pg["frame_out"]
            name = pg["page"].split("(")[0].strip()
            if "スカル" in name and (b - a) <= 24 * 40:      # 30秒版
                gal += [(a + 24 * 3, name + " 点灯中"), (a + 24 * 11, name + " 左向き"), (a + 24 * 19, name + " 右向き"),
                        (a + 24 * 25, name + " 顎開")]
            elif "スカル" in name:
                gal += [(a + 24 * 7, name + " 点灯直後"), (a + 24 * 23, name + " 90°"), (a + 24 * 37, name + " 180°"),
                        (a + 24 * 69, name + " 顎開")]
            elif "ランタン" in name:
                gal += [(a + 24 * 8, name), (a + 24 * 16, name + " 揺れ")]
            elif "コウモリ" in name:
                gal += [(a + 24 * 6, name), (a + 24 * 13, name + " 羽ばたき")]
            elif "HAPPY" in name:
                gal += [(a + 24 * 12, name + " 白"), (a + 24 * 21, name + " 橙")]
            else:
                gal.append(((a + b) // 2, name))
    else:
        gal = [(f, "") for f in range(0, sc.frame_end, 24 * 20)]
    gallery_svg(objs, gal, os.path.join(OUT, "gallery_front.svg"))
    print("gallery svg written")

    if os.environ.get("SHOW_RENDER", "1") != "0":
        samples = int(os.environ.get("SHOW_SAMPLES", "16"))
        render_frames(gal, samples=samples)
        skull = [g for g in gal if "スカル" in g[1]]
        render_frames(skull, samples=samples, cam="DetailCam", prefix="detail")
        render_frames([g for g in gal if "スカル" in g[1]][:1] + [g for g in gal if "ランタン" in g[1]][:1],
                      samples=samples, cam="GroundCam", prefix="ground")
    if os.environ.get("SHOW_VIDEO") == "1":
        # 本編区間を 12fps・640x480 で連番レンダー → ffmpeg があれば mp4 に(DetailCam=スカル拡大)
        sc.render.engine = "CYCLES"
        sc.cycles.samples = int(os.environ.get("SHOW_VIDEO_SAMPLES", "6"))
        sc.render.resolution_x, sc.render.resolution_y = 640, 480
        sc.camera = bpy.data.objects[os.environ.get("SHOW_VIDEO_CAM", "DetailCam")]
        sc.render.use_compositing = True
        vd = os.path.join(OUT, "video_frames")
        os.makedirs(vd, exist_ok=True)
        f0, f1 = (plan["content_frames"] if plan and "content_frames" in plan else (0, sc.frame_end))
        step = 2  # 12 fps
        n = 0
        for f in range(f0 - 24, f1 + 24, step):
            path = os.path.join(vd, f"f{n:05d}.png")
            n += 1
            if os.path.exists(path):
                continue
            sc.frame_set(f)
            sc.render.filepath = path
            bpy.ops.render.render(write_still=True)
        ffmpeg = None
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            import shutil
            ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            import subprocess
            mp4 = os.path.join(OUT, "preview_content.mp4")
            subprocess.run([ffmpeg, "-y", "-framerate", "12", "-i", os.path.join(vd, "f%05d.png"),
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", mp4], check=False)
            print("video:", mp4)
    print("done")


if __name__ == "__main__":
    main()
