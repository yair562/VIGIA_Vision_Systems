import cv2

cam = cv2.VideoCapture(0)

def capture_pc():

    if not cam.isOpened():
        return None

    ret, frame = cam.read()

    if not ret:
        return None

    return frame