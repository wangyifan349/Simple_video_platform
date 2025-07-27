import cv2
import face_recognition
import numpy as np

# ------------------------------------------------------------------
# Function: estimate_blurriness
# Use the variance of the Laplacian to estimate image sharpness.
# Higher variance => sharper image.
# Input: gray_image (numpy array)
# Output: variance value (float)
# ------------------------------------------------------------------
def estimate_blurriness(gray_image):
    return cv2.Laplacian(gray_image, cv2.CV_64F).var()
# ------------------------------------------------------------------
# Function: process_image
# Detect faces, landmarks, encode faces, and estimate blurriness.
# Input: image_path (string)
# Output: list of face_info dictionaries
#   face_info contains:
#     - 'index': face index in this image
#     - 'location': (top, right, bottom, left)
#     - 'landmarks': dict of facial landmarks
#     - 'encoding': 128-dim list
#     - 'blurriness': float
# ------------------------------------------------------------------
def process_image(image_path):
    # Read the image in BGR format
    bgr_image = cv2.imread(image_path)
    if bgr_image is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    # Convert to RGB for face_recognition, and to grayscale for blurriness
    rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
    gray_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)

    # 1. Face detection (returns list of (top, right, bottom, left))
    face_locations = face_recognition.face_locations(rgb_image, model='hog')
    # 2. Facial landmarks
    landmarks_list = face_recognition.face_landmarks(rgb_image, face_locations)

    # 3. Face encodings (128-dim vectors)
    encodings_list = face_recognition.face_encodings(rgb_image, face_locations)
    faces_info = []
    for idx, (loc, landmarks, encoding) in enumerate(zip(face_locations, landmarks_list, encodings_list)):
        top, right, bottom, left = loc
        # Crop the face region in grayscale to estimate blurriness
        face_gray = gray_image[top:bottom, left:right]
        blurriness = float(estimate_blurriness(face_gray))
        face_info = {
            'index': idx,
            'location': {'top': top, 'right': right, 'bottom': bottom, 'left': left},
            'landmarks': landmarks,           # dict of lists of (x,y)
            'encoding': encoding.tolist(),    # convert numpy array to list
            'blurriness': blurriness
        }
        faces_info.append(face_info)
    return faces_info
# ------------------------------------------------------------------
# Function: compare_faces
# Compare two lists of 128-dim face encodings.
# Input: encodings_a, encodings_b (both lists of lists), threshold (float)
# Output: distance_matrix, match_matrix
#   distance_matrix[i][j] = euclidean distance between a_i and b_j
#   match_matrix[i][j] = True if distance <= threshold else False
# ------------------------------------------------------------------
def compare_faces(encodings_a, encodings_b, threshold=0.6):
    A = [np.array(e) for e in encodings_a]
    B = [np.array(e) for e in encodings_b]

    distance_matrix = []
    match_matrix = []

    for a in A:
        distances = face_recognition.face_distance(B, a)
        matches = distances <= threshold
        distance_matrix.append([float(d) for d in distances])
        match_matrix.append([bool(m) for m in matches])

    return distance_matrix, match_matrix

# ------------------------------------------------------------------
# Function: annotate_image
# Draw face boxes and landmarks on the image.
# Input: image_path, list of face_info
# Output: annotated BGR image (numpy array)
# ------------------------------------------------------------------
def annotate_image(image_path, faces_info):
    image = cv2.imread(image_path)
    for face in faces_info:
        loc = face['location']
        top, right, bottom, left = loc['top'], loc['right'], loc['bottom'], loc['left']
        # Draw rectangle
        cv2.rectangle(image, (left, top), (right, bottom), (0, 255, 0), 2)
        # Draw landmarks
        for feature_points in face['landmarks'].values():
            for (x, y) in feature_points:
                cv2.circle(image, (x, y), 2, (0, 0, 255), -1)
    return image

# ------------------------------------------------------------------
# Main routine
# ------------------------------------------------------------------
if __name__ == '__main__':
    img_path1 = 'person1.jpg'
    img_path2 = 'person2.jpg'

    print("Processing image 1...")
    faces1 = process_image(img_path1)
    print(f"Found {len(faces1)} face(s) in image 1.")

    print("Processing image 2...")
    faces2 = process_image(img_path2)
    print(f"Found {len(faces2)} face(s) in image 2.")

    if not faces1 or not faces2:
        print("At least one image has no detectable faces. Exiting.")
        exit(1)

    # Extract encodings
    encodings1 = [f['encoding'] for f in faces1]
    encodings2 = [f['encoding'] for f in faces2]

    # Compare faces
    distance_matrix, match_matrix = compare_faces(encodings1, encodings2, threshold=0.6)

    # Print results
    print("\nFace Comparison Results (* indicates match distance<=0.6):")
    for i, (dist_row, match_row) in enumerate(zip(distance_matrix, match_matrix)):
        for j, (d, m) in enumerate(zip(dist_row, match_row)):
            star = '*' if m else ''
            print(f"Face A[{i}] vs Face B[{j}]: Distance = {d:.3f} {star}")

    # Show annotated images
    annotated1 = annotate_image(img_path1, faces1)
    annotated2 = annotate_image(img_path2, faces2)
    cv2.imshow('Annotated Image 1', annotated1)
    cv2.imshow('Annotated Image 2', annotated2)
    print("Press any key to close windows.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()
