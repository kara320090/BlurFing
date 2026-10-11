import cv2

def width_frame(rgb,size):
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    resized=cv2.resize(gray,(size,size),interpolation=cv2.INTER_AREA if size<gray.shape[1] else cv2.INTER_CUBIC)
    return cv2.createCLAHE(clipLimit=2,tileGridSize=(8,8)).apply(resized)
