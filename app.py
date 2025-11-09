import os
from flask import Flask, jsonify, redirect, url_for, send_from_directory, render_template
from config import Config
from backend.ml_model.model_loader import ModelLoader
from flask_jwt_extended import JWTManager 

# Import DatabaseService for context teardown
from backend.services.database_service import DatabaseService

# Import PredictService class (for instantiation)
from backend.ml_model.predict_service import PredictService

# Import all Blueprint objects (API routes)
from backend.api.auth_routes import auth_bp
from backend.api.user_routes import user_bp
from backend.api.scan_routes import scan_bp 
from backend.api.admin_routes import admin_bp
from backend.api.trash_routes import trash_bp
from backend.api.gallery_routes import gallery_bp 

# Import modules for global service assignment
import backend.api.scan_routes as scan_routes 
import backend.api.admin_routes as admin_routes_module
from backend.models.admin_model import AdminModel


# --- Application Factory Function ---
def create_app(config_class=Config):
    """Initializes and configures the Flask application."""
    app = Flask(__name__, 
                static_folder='src/static',
                template_folder='src/templates')
    
    app.config.from_object(config_class)

    # CRITICAL: Flask-JWT-Extended requires JWT_SECRET_KEY.
    if 'SECRET_KEY' in app.config and 'JWT_SECRET_KEY' not in app.config:
        app.config['JWT_SECRET_KEY'] = app.config['SECRET_KEY']

    # Initialize Flask-JWT-Extended 
    jwt = JWTManager(app) 
    
    # Ensure the upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # --- 1. Register Blueprints (API Routes) ---
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(user_bp, url_prefix='/api/user')
    app.register_blueprint(scan_bp, url_prefix='/api/scan')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(trash_bp, url_prefix='/api/trash')
    app.register_blueprint(gallery_bp, url_prefix='/api/gallery') 

    # --- 2. Load Machine Learning Model ---
    app.logger.info("Starting ML model loading...")
    model_loaded = False
    
    try:
        ModelLoader.load_model(app.config['MODEL_PATH'])
        app.logger.info("ML model successfully loaded.")
        model_loaded = True
    except RuntimeError as e:
        app.logger.error(f"CRITICAL: ML Model failed to load: {e}. Scan functionality will be disabled.")
        # This block no longer raises the error, allowing the app to start cleanly.
        model_loaded = False

    # --- 3. Initialize Services requiring context/config ---
    with app.app_context():
        # FIX: Only initialize PredictService IF the model loaded
        if model_loaded:
            scan_routes.predict_service = PredictService()
        else:
            scan_routes.predict_service = None 
            
        admin_routes_module.admin_model = AdminModel(
            disease_classes=app.config.get('DISEASE_CLASSES')
        )

    # --- 4. Serve Static HTML Pages (Frontend Routes) ---
    
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/login')
    def login_page():
        return render_template('auth/login.html')

    @app.route('/signup')
    def signup_page():
        return render_template('auth/signup.html')

    # FIX: Add routes for Forgot Password workflow
    @app.route('/forgot-password')
    def forgot_password_page():
        return render_template('auth/forgot_password.html')

    @app.route('/reset-password-confirm')
    def reset_password_page():
        return render_template('auth/reset_password.html')
        
    @app.route('/dashboard')
    def dashboard_page():
        return render_template('user/dashboard.html')

    @app.route('/scan')
    def scan_page():
        return render_template('user/scan.html')

    @app.route('/gallery')
    def gallery_page():
        return render_template('user/gallery.html')

    @app.route('/settings')
    def settings_page():
        return render_template('user/settings.html')
        
    @app.route('/feedback')
    def feedback_page():
        return render_template('user/feedback.html')
        
    @app.route('/tree/<int:tree_id>')
    def tree_detail_page(tree_id):
        return render_template('user/tree_detail.html')
        
    # --- Admin Routes ---
    
    @app.route('/admin/dashboard')
    def admin_dashboard_page():
        # FIX: Ensure the correct ADMIN dashboard template is rendered
        return render_template('user/admin/dashboard.html')
    
    @app.route('/admin/feedbacks')
    def admin_feedbacks_page():
        return render_template('user/admin/feedbacks.html')
    
    @app.route('/admin/diseases')
    def admin_diseases_page():
        return render_template('user/admin/disease.html')

    @app.route('/admin/users')
    def admin_users_page():
        return render_template('user/admin/users.html') 

    @app.route('/admin/images')
    def admin_images_page():
        # FIX: Route for the Admin All Scans page
        return render_template('user/admin/images.html') 

    # --- User Utility Routes ---

    @app.route('/user/statistic')
    def user_statistic_page():
        return render_template('user/statistic.html')

    @app.route('/user/trash')
    def user_trash_page():
        return render_template('user/tash.html')
        
    @app.route('/regional-report') # <-- NEW ROUTE
    def regional_report_page():
        return render_template('user/regional_report.html')
        
    @app.route('/uploads/<path:filename>')
    def serve_uploaded_file(filename):
        """Serves images uploaded by users from the UPLOAD_FOLDER."""
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    # --- 5. Final Configuration and Teardown ---

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Not Found", "message": "The requested URL was not found on the server."}), 404
        
    # CRITICAL: Register the non-pooled teardown function
    app.teardown_appcontext(DatabaseService.close_db_connection)

    # Final return statement must be here
    return app

# If running directly (e.g., via 'python app.py')
if __name__ == '__main__':
    # Set the SECRET_KEY for session management (temporary)
    os.environ['SECRET_KEY'] = 'dev-key-please-change-in-prod' 
    
    # Create the app object
    app = create_app(Config) 
    
    # Host on 0.0.0.0 to be accessible externally (useful for development)
    app.run(host='0.0.0.0', port=5000)