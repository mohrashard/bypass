import os
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

model_path = "selfie_segmenter.tflite"
base_options = python.BaseOptions(model_asset_path=model_path)
options = vision.ImageSegmenterOptions(base_options=base_options, output_confidence_masks=True, output_category_mask=False)
with vision.ImageSegmenter.create_from_options(options) as segmenter:
    frame_rgb = np.zeros((480, 640, 3), dtype=np.uint8)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
    res = segmenter.segment(mp_image)
    print("Num confidence masks:", len(res.confidence_masks))
    for i, m in enumerate(res.confidence_masks):
        mask = m.numpy_view()
        print(f"Mask {i} shape: {mask.shape}, min: {mask.min()}, max: {mask.max()}")
