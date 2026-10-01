# blob-rects

Finds blobs in a binary mask and fits each one with the rotated rectangle that maximizes IoU. Writes the rectangles to a CSV.

```
uv sync
uv run blob-rects mask.png --output boxes.csv --image-output boxes.png
```

Notes:

- Pixels are 8-connected, so diagonal neighbours belong to the same blob.
- Works best on mostly convex blobs without holes. Non-convex ones can end up in a local minimum.
- The optimizer favours accuracy over speed, so expect a few seconds per image.
