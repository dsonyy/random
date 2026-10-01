from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import NamedTuple

import cv2
import numpy as np
import shapely
from PIL import Image
from scipy.optimize import minimize


EPSILON = 1e-9


class Rect(NamedTuple):
    center_x: float
    center_y: float
    width: float
    height: float
    angle: float


class Blob(NamedTuple):
    blob_id: int
    submask: np.ndarray
    x: int
    y: int


def load_binary_mask(path: Path) -> np.ndarray:
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        with Image.open(path) as im:
            if im.mode not in ("L", "1"):
                print(
                    f"warning: image is not grayscale (mode={im.mode})", file=sys.stderr)
            array = np.array(im.convert("L"))
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: failed to read image: {exc}", file=sys.stderr)
        sys.exit(2)

    if not np.isin(array, (0, 255)).all():
        print("error: image is not a binary mask (values other than 0/255 found)", file=sys.stderr)
        sys.exit(3)

    normalized = (array == 255).astype(np.uint8)

    return normalized


def find_blobs(binary: np.ndarray) -> list[Blob]:
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        binary, connectivity=8)

    blobs: list[Blob] = []
    for label_id in range(1, num_labels):
        x, y, w, h, _ = stats[label_id]
        submask = labels[y: y + h, x: x + w] == label_id
        blobs.append(Blob(label_id, submask, x, y))
    return blobs


def build_rect_polygon(cx: float, cy: float, w: float, h: float, angle_deg: float) -> shapely.Geometry:
    # Build an axis-aligned w x h rectangle centered on the origin, then
    # rotate it and move it to (cx, cy). Gives the 4 exact corner points of
    # a candidate rectangle, as a polygon we can measure overlap area with.
    theta = np.deg2rad(angle_deg)
    cos_t, sin_t = np.cos(theta), np.sin(theta)
    hw, hh = w / 2.0, h / 2.0
    local = np.array([[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]])
    rot = np.array([[cos_t, -sin_t], [sin_t, cos_t]])
    world = local @ rot.T + np.array([cx, cy])
    return shapely.Polygon(world)


def build_blob_polygon(submask: np.ndarray) -> shapely.Geometry:
    # A pixel is not a point, it's a 1x1 unit square. So the blob's exact
    # shape is the union of one unit square per foreground pixel. Building
    # it this way (instead of rasterizing a candidate rectangle onto a grid)
    # avoids pixel-quantization error when measuring overlap.
    ys, xs = np.nonzero(submask)
    boxes = shapely.box(xs, ys, xs + 1, ys + 1)
    return shapely.union_all(boxes)


def compute_iou(blob_poly: shapely.Geometry, cx: float, cy: float, w: float, h: float, angle: float) -> float:
    if w <= EPSILON or h <= EPSILON:
        return 0.0

    rect = build_rect_polygon(cx, cy, w, h, angle)
    if not rect.is_valid or rect.area <= EPSILON:
        return 0.0

    inter = blob_poly.intersection(rect).area
    union = blob_poly.area + rect.area - inter
    if union <= EPSILON:
        return 0.0

    return inter / union


def normalize_angle(angle: float) -> float:
    # returns angle in [-90, 90)
    return ((angle + 90.0) % 180.0) - 90.0


def normalize_rect(cx: float, cy: float, w: float, h: float, angle: float) -> Rect:
    w, h = abs(w), abs(h)
    if w < h:
        w, h = h, w
        angle += 90.0
    return Rect(cx, cy, w, h, normalize_angle(angle))


def fit_rectangle(submask: np.ndarray) -> Rect:
    # foreground pixel coordinates of this one blob
    ys, xs = np.nonzero(submask)

    if len(xs) == 1:
        # A single pixel's case is trivial
        return Rect(float(xs[0]) + 0.5, float(ys[0]) + 0.5, 1.0, 1.0, 0.0)

    # build the starting point for iou optimization
    points = np.column_stack([xs, ys]).astype(np.float32)
    (mcx, mcy), (mw, mh), mangle = cv2.minAreaRect(points)
    seed = Rect(float(mcx), float(mcy), float(mw) +
                1.0, float(mh) + 1.0, float(mangle))

    # build blob polygon, from rasterized pixels
    poly = build_blob_polygon(submask)

    # optimize the shape for further calculations
    shapely.prepare(poly)

    # build and ude the optimizer
    def loss(params: np.ndarray) -> float:
        cx, cy, w, h, angle = params
        return 1.0 - compute_iou(poly, cx, cy, w, h, angle)
    best_rect, best_iou = seed, 1.0 - loss(np.array(seed))
    result = minimize(
        loss,
        x0=np.array(seed),
        method="Nelder-Mead",
        options={"maxiter": 300,
                 "maxfev": 300,
                 "xatol": 1e-3,
                 "fatol": 1e-4},
    )
    result_iou = 1.0 - result.fun
    if result_iou > best_iou:
        best_iou, best_rect = result_iou, Rect(
            float(result.x[0]),
            float(result.x[1]),
            float(result.x[2]),
            float(result.x[3]),
            float(result.x[4]),
        )

    # normalize the rect
    rect = normalize_rect(*best_rect)

    return rect


def fit_rectangles(binary: np.ndarray) -> list[dict[str, float]]:
    blobs = find_blobs(binary)
    results: list[dict[str, float]] = []
    for blob_id, submask, x, y in blobs:
        cx, cy, rw, rh, angle = fit_rectangle(submask)
        results.append(
            {
                "blob_id": blob_id,
                "center_x": cx + x,
                "center_y": cy + y,
                "width": rw,
                "height": rh,
                "angle": angle,
            }
        )
    return results


def write_csv(results: list[dict[str, float]], path: Path) -> None:
    fieldnames = ["blob_id", "center_x",
                  "center_y", "width", "height", "angle"]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def write_image_output(binary: np.ndarray, results: list[dict[str, float]], path: Path) -> None:
    canvas = cv2.cvtColor(binary * 255, cv2.COLOR_GRAY2BGR)
    for row in results:
        box = cv2.boxPoints(
            ((row["center_x"], row["center_y"]),
             (row["width"], row["height"]), row["angle"])
        )
        cv2.drawContours(canvas, [box.astype(np.int32)], 0, (0, 0, 255), 1)
    cv2.imwrite(str(path), canvas)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect blobs in a binary mask and fit IoU-maximizing rotated rectangles."
    )
    parser.add_argument("image", type=Path,
                        help="path to the grayscale binary mask image")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("blob_bounding_boxes.csv"), help="output CSV path (default: output.csv)"
    )
    parser.add_argument(
        "-i", "--image-output", type=Path, default=None, help="optional path to save a visualization image"
    )
    args = parser.parse_args()

    binary = load_binary_mask(args.image)

    try:
        results = fit_rectangles(binary)

        write_csv(results, args.output)
        if args.image_output is not None:
            write_image_output(binary, results, args.image_output)
    except Exception as exc:
        print(f"error: processing failed: {exc}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
