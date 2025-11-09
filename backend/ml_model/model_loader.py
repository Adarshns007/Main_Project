import tensorflow as tf
from tensorflow.keras.models import load_model

class ModelLoader:
    """
    Manages the singleton instance of the TensorFlow/Keras CNN model.
    The model is loaded once at application startup.
    """
    _model = None

    @classmethod
    def load_model(cls, model_path: str):
        """
        Loads the model from the specified path.
        This operation should only be performed once.
        """
        if cls._model is None:
            try:
                # Load the H5 model
                cls._model = load_model(model_path)
                # Recompile with the default optimizer/loss for prediction mode (optional but good practice)
                cls._model.compile(optimizer='adam', loss='categorical_crossentropy', metrics=['accuracy'])
                
            except Exception as e:
                # Log the error and raise an exception if the model fails to load
                raise RuntimeError(f"Failed to load the ML model from {model_path}: {e}")

    @classmethod
    def get_model(cls) -> tf.keras.Model:
        """
        Returns the loaded model instance.
        Raises an error if the model has not been loaded yet.
        """
        if cls._model is None:
            raise RuntimeError("ML Model has not been loaded. Call load_model() first.")
        return cls._model

# Placeholder for image pre-processing utility (will be detailed later)
def preprocess_image(image_data, target_size=(224, 224)):
    """
    Converts raw image data (e.g., bytes or file path) into a numpy array 
    ready for model prediction.
    """
    from PIL import Image
    import numpy as np
    
    # Assuming image_data is a file object or path for simplicity here
    img = Image.open(image_data).convert('RGB')
    img = img.resize(target_size)
    
    # Convert image to numpy array and normalize
    img_array = np.asarray(img)
    img_array = img_array / 255.0  # Normalization
    
    # Expand dimensions to create a batch size of 1 (required by the model)
    img_array = np.expand_dims(img_array, axis=0)
    
    return img_array