import numpy as np
from PIL import Image
from io import BytesIO
from flask import current_app
from .model_loader import ModelLoader
import cv2 

class PredictService:
    """
    Handles all pre-processing, prediction execution, and post-processing 
    for the mango leaf disease classification model.
    """
    
    def __init__(self):
        # Retrieve configuration constants
        self.classes = current_app.config['DISEASE_CLASSES']
        self.image_size = current_app.config['IMAGE_SIZE']
        self.color_mode = current_app.config['COLOR_MODE']
        self.model = ModelLoader.get_model()
        # FIX: Define a blur threshold 
        self.BLUR_THRESHOLD = 30.0 # Standard threshold value

    def _preprocess_image(self, image_file_storage):
        """
        Loads the image from FileStorage, resizes it, and converts it to a 
        model-ready numpy array. Includes blur detection and rejection.
        """
        try:
            # 1. Load Image from FileStorage
            image_data = image_file_storage.read()
            img_stream = BytesIO(image_data)
            img = Image.open(img_stream)
            
            # 2. Convert and Resize for ML Model
            img_resized = img.convert('RGB').resize(self.image_size)
            
            # 3. Blur Detection (Perform on resized image for efficiency)
            # Convert PIL image to OpenCV format (NumPy array)
            img_array_cv = np.asarray(img_resized, dtype=np.uint8)
            gray = cv2.cvtColor(img_array_cv, cv2.COLOR_RGB2GRAY)
            
            # Compute the Laplacian variance (a measure of image sharpness/blur)
            variance_of_laplacian = cv2.Laplacian(gray, cv2.CV_64F).var()

            if variance_of_laplacian < self.BLUR_THRESHOLD:
                # Reject the image if too blurry
                current_app.logger.warning(f"Image rejected: Blur score ({variance_of_laplacian:.2f}) below threshold ({self.BLUR_THRESHOLD}).")
                # FIX: Raise a clean ValueError for the user
                raise ValueError("Image is too blurry. Please upload a clear photo of the leaf.")
            
            # 4. Final Preprocessing for Model
            img_array = np.asarray(img_resized, dtype=np.float32)
            
            # Normalize pixel values (0-255 to 0.0-1.0)
            img_array = img_array / 255.0
            
            # Expand dimensions to create a batch size of 1
            return np.expand_dims(img_array, axis=0)

        except ValueError as ve:
            # Re-raise explicit ValueError for blur rejection
            raise ve
        except Exception as e:
            current_app.logger.error(f"Image preprocessing failed: {e}")
            raise ValueError("Invalid image file, format, or server preprocessing error.")


    def analyze_image(self, image_file_storage):
        """
        Runs the full prediction pipeline: preprocess, predict, post-process.
        Returns a dictionary with the prediction result.
        """
        # 1. Preprocess (This will now consume the stream and check for blur)
        model_input = self._preprocess_image(image_file_storage) 

        # 2. Predict
        predictions = self.model.predict(model_input)[0] 

        # 3. Post-process
        
        # Get the index of the highest probability
        max_confidence_index = np.argmax(predictions)
        
        # Get the predicted class name and its confidence score
        predicted_class = self.classes[max_confidence_index]
        confidence_score = float(predictions[max_confidence_index]) 
        
        # Format raw probabilities for the database
        raw_output = {}
        for i, prob in enumerate(predictions):
            raw_output[self.classes[i]] = float(prob)

        # Return the structured result
        return {
            "predicted_class": predicted_class,
            "confidence_score": confidence_score,
            "raw_output": raw_output
        }