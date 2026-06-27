import cv2
import os

def extract_frames(video_path, output_dir, interval=20, prefix="xinbu"):
    """
    Extract frames from a video every 'interval' frames and save them as images.
    """
    # Ensure the output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Open the video file
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print(f"Error: Could not open video {video_path}")
        return

    frame_count = 0
    saved_count = 0

    while True:
        # Read the next frame from the video
        ret, frame = cap.read()
        
        # If no frame is returned, we have reached the end of the video
        if not ret:
            break

        # Check if the current frame is a multiple of the interval
        if frame_count % interval == 0:
            output_filename = f"{prefix}_{frame_count}.jpg"
            output_filepath = os.path.join(output_dir, output_filename)
            
            # Save the frame
            cv2.imwrite(output_filepath, frame)
            saved_count += 1
            print(f"Saved: {output_filepath}")

        frame_count += 1

    # Release the video capture object
    cap.release()
    print(f"Done! Extracted {saved_count} frames to {output_dir}")

if __name__ == "__main__":
    # Get the directory where this script is located
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Path to the specific video file
    video_file = os.path.join(current_dir, "JAT_6.mp4")
    
    # Path to the output directory+
    output_folder = os.path.join(current_dir, "datas\JAT")
    
    print("Starting frame extraction...")
    extract_frames(video_file, output_folder, interval=20, prefix="JAT6")