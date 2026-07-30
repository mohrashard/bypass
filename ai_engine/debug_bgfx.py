import subprocess
import json

options = {
    "timelineScenes": [{
        "timestamp": 0.0,
        "bgImagePath": "c:\\Projects\\capcut-bypass\\ai_engine\\assets\\side.png",
        "bgScale": 100,
        "subjectScale": 100,
        "subjectY": 0,
        "textBehind": "DM",
        "textY": 50,
        "textSize": 100
    }],
    "bgMode": "image",
    "keyingMode": "chroma"
}

import sys
sys.path.append("c:\\Projects\\capcut-bypass\\ai_engine")
from pipeline import stage_background_fx

try:
    # use any short video for testing
    stage_background_fx("c:\\Projects\\capcut-bypass\\ai_engine\\assets\\sample.mp4", options)
except Exception as e:
    print(str(e))
