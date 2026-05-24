import os
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import urllib.request

model_path = "selfie_segmenter.tflite"
if not os.path.exists(model_path):
    urllib.request.urlretrieve("https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite", model_path)

base_options = python.BaseOptions(model_asset_path=model_path)
options = vision.ImageSegmenterOptions(base_options=base_options, output_category_mask=True)
with vision.ImageSegmenter.create_from_options(options) as segmenter:
    frame_rgb = np.zeros((480, 640, 3), dtype=np.uint8)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
    res = segmenter.segment(mp_image)
    mask = res.category_mask.numpy_view()
    print("Mask shape:", mask.shape)
    print("Unique classes:", np.unique(mask))
