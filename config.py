import os

# --- Core Flask Configuration ---
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_super_secret_fallback_key' 
    DEBUG = True
    TESTING = False

    # --- MySQL Database Configuration ---
    # These variables should be set in your root .env file
    MYSQL_HOST = os.environ.get('MYSQL_HOST') or 'localhost'
    MYSQL_USER = os.environ.get('MYSQL_USER') or 'root'
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD') or 'adarsh'
    MYSQL_DB = os.environ.get('MYSQL_DB') or 'leafguard_db'
    
    # --- Machine Learning Configuration ---
    # Path to the model file
    MODEL_PATH = 'ml_model_files/mango_leaf_classifier_98_plus_final.h5'
    
    # IMPORTANT: The classes MUST be in the exact order the model was trained on
    # Total classes: 8
    DISEASE_CLASSES = [
        'Anthracnose', 
        'Bacterial Canker', 
        'Cutting Weevil',
        'die back',
        'Gall Midge',
        'Healthy', 
        'Powdery Mildew', 
        'Sooty Mould'
    ]

    # Model input parameters (adjust based on your model's requirement)
    IMAGE_SIZE = (224, 224)
    COLOR_MODE = 'rgb' # or 'grayscale'
    
    # --- File Upload Configuration ---
    UPLOAD_FOLDER = 'backend/uploads/images'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# Subclass for environment-specific settings (optional)
class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get('SECRET_KEY')