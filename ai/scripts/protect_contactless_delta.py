import cv2

import numpy as np

def normalize_contactless(gray512):
    a=np.asarray(gray512)
    if a.dtype!=np.uint8 or a.shape!=(512,512):raise ValueError('Expected 512x512 uint8 gray')
    return cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8)).apply(a)
