# backend/api/user_routes.py

from flask import Blueprint, request, jsonify, current_app, url_for
from backend.models.farm_model import FarmModel
from backend.models.tree_model import TreeModel
from backend.models.image_model import ImageModel 
from backend.models.feedback_model import FeedbackModel
from backend.models.statistics_model import StatisticsModel
from backend.models.user_model import UserModel 
from backend.models.disease_model import DiseaseModel # <-- ADDED IMPORT
from functools import wraps
from flask_jwt_extended import jwt_required, get_jwt_identity 
from backend.api.geo_utils import haversine_distance # Import Haversine utility

# Create Blueprint
user_bp = Blueprint('user_bp', __name__)
farm_model = FarmModel()
tree_model = TreeModel()
image_model = ImageModel()
feedback_model = FeedbackModel()
statistics_model = StatisticsModel()
user_model = UserModel()
disease_model = DiseaseModel() # <-- INITIALIZED

# --- Authentication Decorator (FINAL FIX APPLIED HERE) ---
def token_required(fn):
    """
    Decorator that protects API endpoints. 
    Enforces that the user ID passed to the route function is a Python INTEGER.
    """
    @wraps(fn)
    @jwt_required() 
    def wrapper(*args, **kwargs):
        try:
            # 1. Retrieve the identity (which may be a string from the JWT)
            current_id_str = get_jwt_identity()
            # 2. CRITICAL FIX: Explicitly cast to integer here to prevent repeated crash
            current_user_id = int(current_id_str) 
        except Exception as e:
            current_app.logger.error(f"JWT Identity Error: {e}")
            return jsonify({"message": "Invalid authentication token identity format."}), 401
        
        # Pass the verified integer user ID to the route function
        kwargs['current_user_id'] = current_user_id
        return fn(*args, **kwargs)
    return wrapper

# ==============================================================================
# --- Farm Routes (/api/user/farm) ---
# ... (omitted existing farm routes for brevity) ...

@user_bp.route('/farm', methods=['POST'])
@token_required
def create_farm_route(current_user_id):
    """Creates a new farm with optional coordinates."""
    data = request.get_json()
    farm_name = data.get('farm_name')
    location_details = data.get('location_details')
    # FIX: Retrieve latitude and longitude for geo-fencing feature
    latitude = data.get('latitude') 
    longitude = data.get('longitude') 

    if not farm_name:
        return jsonify({"message": "Farm name is required"}), 400

    # FIX: Pass new coordinates to the model
    new_farm_id = farm_model.create_farm(current_user_id, farm_name, location_details, latitude, longitude)
    
    if new_farm_id:
        return jsonify({"message": "Farm created successfully", "farm_id": new_farm_id}), 201
    return jsonify({"message": "Failed to create farm"}), 500

@user_bp.route('/farm', methods=['GET'])
@token_required
def get_farms_route(current_user_id):
    """Retrieves all farms for the current user."""
    farms = farm_model.get_all_user_farms(current_user_id)
    
    # FIX: Ensure farms is an iterable (list) to prevent AttributeError/TypeError crash.
    if farms is None:
        farms = []
        current_app.logger.error(f"Database query failed for user {current_user_id} when fetching farms. Returning empty list.")
    
    # Ensure dates/times are serializable if they exist in the farm objects
    for farm in farms:
        if farm.get('created_at'):
            farm['created_at'] = farm['created_at'].isoformat()
            
    return jsonify(farms), 200

@user_bp.route('/farm/<int:farm_id>', methods=['GET', 'PUT', 'DELETE'])
@token_required
def manage_farm_route(farm_id, current_user_id):
    """Manages a specific farm (Read, Update, Delete)."""
    
    farm = farm_model.get_farm_by_id(farm_id, current_user_id)
    if not farm:
        return jsonify({"message": "Farm not found or unauthorized"}), 404

    if request.method == 'GET':
        # Ensure dates/times are serializable
        if farm.get('created_at'):
            farm['created_at'] = farm['created_at'].isoformat()
        return jsonify(farm), 200

    elif request.method == 'PUT':
        data = request.get_json()
        farm_name = data.get('farm_name', farm['farm_name'])
        location_details = data.get('location_details', farm['location_details'])
        # FIX: Handle latitude and longitude updates
        latitude = data.get('latitude', farm.get('latitude'))
        longitude = data.get('longitude', farm.get('longitude'))
        
        if farm_model.update_farm(farm_id, current_user_id, farm_name, location_details, latitude, longitude):
            return jsonify({"message": "Farm updated successfully"}), 200
        return jsonify({"message": "Update failed"}), 500

    elif request.method == 'DELETE':
        if farm_model.delete_farm(farm_id, current_user_id):
            return jsonify({"message": "Farm deleted successfully"}), 200
        return jsonify({"message": "Delete failed"}), 500

# ==============================================================================
# --- Tree Routes (/api/user/tree) ---
# ... (omitted existing tree routes for brevity) ...

@user_bp.route('/tree', methods=['POST'])
@token_required
def create_tree_route(current_user_id):
    """Creates a new tree linked to a farm."""
    data = request.get_json()
    farm_id = data.get('farm_id')
    tree_name = data.get('tree_name')
    age_years = data.get('age_years')
    planting_date = data.get('planting_date') # Expects YYYY-MM-DD format

    if not all([farm_id, tree_name]):
        return jsonify({"message": "Farm ID and tree name are required"}), 400

    if not farm_model.get_farm_by_id(farm_id, current_user_id):
        return jsonify({"message": "Farm not found or unauthorized"}), 404

    new_tree_id = tree_model.create_tree(farm_id, tree_name, age_years, planting_date)
    
    if new_tree_id:
        return jsonify({"message": "Tree created successfully", "tree_id": new_tree_id}), 201
    return jsonify({"message": "Failed to create tree"}), 500

@user_bp.route('/farm/<int:farm_id>/tree', methods=['GET'])
@token_required
def get_trees_by_farm_route(farm_id, current_user_id):
    """Retrieves all trees for a specific farm, ensuring user ownership."""
    
    if not farm_model.get_farm_by_id(farm_id, current_user_id):
        return jsonify({"message": "Farm not found or unauthorized"}), 404
        
    trees = tree_model.get_all_trees_by_farm(farm_id)
    
    if trees is None:
        trees = []
        current_app.logger.error(f"Database query failed for user {current_user_id} when fetching trees for farm {farm_id}. Returning empty list.")
        
    return jsonify(trees), 200

@user_bp.route('/tree/<int:tree_id>', methods=['GET', 'PUT', 'DELETE'])
@token_required
def manage_tree_route(tree_id, current_user_id):
    """Manages a specific tree (Read, Update, Delete)."""
    
    tree = tree_model.get_tree_by_id(tree_id)
    if not tree:
        return jsonify({"message": "Tree not found"}), 404
    
    farm = farm_model.get_farm_by_id(tree['farm_id'], current_user_id)
    if not farm:
        return jsonify({"message": "Tree not found or unauthorized access"}), 404

    if request.method == 'GET':
        if tree.get('planting_date'):
            tree['planting_date'] = tree['planting_date'].isoformat()
        return jsonify({**tree, "farm_name": farm['farm_name']}), 200

    elif request.method == 'PUT':
        data = request.get_json()
        tree_name = data.get('tree_name', tree['tree_name'])
        age_years = data.get('age_years', tree['age_years'])
        planting_date = data.get('planting_date', tree['planting_date'])

        if tree_model.update_tree(tree_id, tree_name, age_years, planting_date):
            return jsonify({"message": "Tree updated successfully"}), 200
        return jsonify({"message": "Update failed"}), 500

    elif request.method == 'DELETE':
        if tree_model.delete_tree(tree_id):
            return jsonify({"message": "Tree deleted successfully"}), 200
        return jsonify({"message": "Delete failed"}), 500

# ==============================================================================
# --- Gallery/Image Detail Route & Tree History (omitted for brevity) ---
# ...
# ==============================================================================

@user_bp.route('/gallery/<int:image_id>', methods=['GET'])
@token_required
def get_image_detail_route(image_id, current_user_id):
    detail = image_model.get_image_details(image_id, current_user_id)
    if not detail:
        return jsonify({"message": "Image not found or unauthorized"}), 404
    filename = detail['file_path'].split('/')[-1]
    detail['file_path'] = url_for('serve_uploaded_file', filename=filename, _external=True)
    if detail.get('upload_date'):
        detail['upload_date'] = detail['upload_date'].isoformat()
    return jsonify(detail), 200

@user_bp.route('/tree/<int:tree_id>/images', methods=['GET'])
@token_required
def get_tree_images_route(tree_id, current_user_id):
    tree = tree_model.get_tree_by_id(tree_id)
    if not tree:
        return jsonify({"message": "Tree not found"}), 404
    farm = farm_model.get_farm_by_id(tree['farm_id'], current_user_id)
    if not farm:
        return jsonify({"message": "Unauthorized access to tree data"}), 403 
    images = image_model.get_images_by_tree(tree_id)
    if images is None:
        images = []
        current_app.logger.error(f"Database query failed for user {current_user_id} when fetching tree images. Returning empty list.")
    for image in images:
        filename = image['file_path'].split('/')[-1]
        image['file_path'] = url_for('serve_uploaded_file', filename=filename, _external=True)
        if image.get('upload_date'):
            image['upload_date'] = image['upload_date'].isoformat()
    return jsonify(images), 200

# ==============================================================================
# --- User Profile and Settings Routes (/api/user) (omitted for brevity) ---
# ...
# ==============================================================================

@user_bp.route('/profile', methods=['GET'])
@token_required
def get_user_profile_route(current_user_id):
    user_profile = user_model.get_user_profile(current_user_id)
    if user_profile is None:
        return jsonify({"message": "Failed to retrieve user profile data due to a server error."}), 500
    if user_profile:
        user_profile.pop('password_hash', None) 
        if user_profile.get('created_at'):
            user_profile['created_at'] = user_profile['created_at'].isoformat()
        return jsonify(user_profile), 200
    return jsonify({"message": "User profile not found"}), 404

@user_bp.route('/', methods=['PUT'])
@token_required
def update_user_profile_route(current_user_id):
    data = request.get_json()
    username = data.get('username')
    if username:
        if user_model.update_user_profile(current_user_id, username):
            return jsonify({"message": "Profile updated successfully"}), 200
        return jsonify({"message": "Failed to update profile or no changes detected"}), 400
    return jsonify({"message": "Invalid fields provided for update"}), 400

@user_bp.route('/password', methods=['PUT'])
@token_required
def update_user_password_route(current_user_id):
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    if not all([current_password, new_password]) or len(new_password) < 6:
        return jsonify({"message": "Invalid password data provided"}), 400
    user = user_model.find_user_by_id(current_user_id)
    if user and user_model.verify_password(user['password_hash'], current_password):
        if user_model.update_user_password(current_user_id, new_password):
            return jsonify({"message": "Password updated successfully. Please log in again."}), 200
        return jsonify({"message": "Failed to update password due to server error"}), 500
    return jsonify({"message": "Invalid current password"}), 401

@user_bp.route('/change-email/send-code', methods=['POST'])
@token_required
def send_email_verification_code_route(current_user_id):
    data = request.get_json()
    new_email = data.get('new_email')
    if not new_email or not user_model.find_user_by_id(current_user_id):
        return jsonify({"message": "Invalid user or email provided."}), 400
    current_app.logger.info(f"MOCK: Sent verification code '123456' to {new_email} for user {current_user_id}.")
    return jsonify({"message": "Verification code sent to your new email address."}), 200

@user_bp.route('/change-email/confirm', methods=['POST'])
@token_required
def confirm_email_change_route(current_user_id):
    data = request.get_json()
    new_email = data.get('new_email')
    code = data.get('code')
    if code == '123456':
        return jsonify({"message": "Email address updated and verified successfully! Please log in again."}), 200
    else:
        return jsonify({"message": "Invalid verification code."}), 401
    
@user_bp.route('/preferences', methods=['PUT'])
@token_required
def update_user_preferences_route(current_user_id):
    data = request.get_json()
    current_app.logger.info(f"MOCK: User {current_user_id} updated preferences: {data}")
    return jsonify({"message": "Preferences saved successfully."}), 200


# ==============================================================================
# --- Geo-Fencing Alert Route (/api/user/outbreak-alert) (omitted for brevity) ---
# ...
# ==============================================================================
@user_bp.route('/outbreak-alert', methods=['GET'])
@token_required
def get_outbreak_alert_route(current_user_id):
    """
    Checks the user's farms against system-wide data for an active geo-outbreak risk.
    """
    try:
        alert_data = statistics_model.check_geo_outbreak_risk(current_user_id, max_distance_km=5.0)
        return jsonify(alert_data), 200
    except Exception as e:
        current_app.logger.error(f"Geo-Outbreak Alert error for user {current_user_id}: {e}")
        return jsonify({"risk_found": False, "message": "Could not check outbreak status."}), 500

# ==============================================================================
# --- Regional Statistics Route (UPDATED) ---
# ==============================================================================
@user_bp.route('/regional-stats', methods=['GET'])
@token_required
def get_regional_statistics_route(current_user_id):
    """
    Retrieves anonymous, aggregated disease statistics calculated by the 
    number of unique affected trees within a 5km radius of the location.
    """
    try:
        latitude = request.args.get('latitude')
        longitude = request.args.get('longitude')
        
        if not latitude or not longitude:
             return jsonify({"message": "Latitude and longitude are required for regional analysis."}), 400

        target_lat = float(latitude)
        target_lon = float(longitude)
        
        # 1. Get aggregated data (now counts unique trees)
        regional_data_full = statistics_model.get_regional_disease_data(target_lat, target_lon, max_distance_km=5.0)
        
        regional_data = regional_data_full['regional_tree_counts'] # KEY CHANGE: Now counts unique trees

        top_treatments = []
        if regional_data:
            # 2. Sort the data by count (descending)
            # This sorting is now based on the number of unique affected trees
            sorted_diseases = sorted(regional_data.items(), key=lambda item: item[1], reverse=True)
            
            # 3. Get the top 2 diseases
            for disease_name, count in sorted_diseases[:2]:
                treatment = disease_model.get_disease_by_name(disease_name)
                if treatment:
                    top_treatments.append({
                        "name": disease_name,
                        "count": count,
                        "organic": treatment['organic_treatment'],
                        "chemical": treatment['chemical_treatment']
                    })

        if not regional_data:
            return jsonify({"regional_data": {}, "top_treatments": [], "message": "No diseased trees found in the 5km radius."}), 200

        return jsonify({
            "regional_data": regional_data, # This is now tree counts
            "top_treatments": top_treatments,
            "message": "Regional data retrieved successfully."
        }), 200
        
    except ValueError:
        return jsonify({"message": "Invalid latitude or longitude format."}), 400
    except Exception as e:
        current_app.logger.error(f"Regional Statistics error for user {current_user_id}: {e}")
        return jsonify({"message": "Could not retrieve regional statistics."}), 500
        
# ==============================================================================
# --- Disease Information Route (NEW) ---
# ==============================================================================
@user_bp.route('/diseases', methods=['GET'])
@token_required
def get_all_diseases_for_user_route(current_user_id):
    """
    Retrieves all disease records for the user to use as a static reference guide.
    """
    try:
        diseases = disease_model.get_all_diseases()
        return jsonify(diseases), 200
    except Exception as e:
        current_app.logger.error(f"User disease list error: {e}")
        return jsonify({"message": "Failed to retrieve disease information list"}), 500


# ==============================================================================
# --- Feedback Routes & Statistics Routes (omitted for brevity) ---
# ...
# ==============================================================================

@user_bp.route('/feedback', methods=['POST'])
@token_required
def create_feedback_route(current_user_id):
    data = request.get_json()
    subject = data.get('subject')
    message = data.get('message')
    rating = data.get('rating')
    if not all([subject, message]):
        return jsonify({"message": "Subject and message are required"}), 400
    feedback_id = feedback_model.create_feedback(current_user_id, subject, message, rating)
    if feedback_id:
        return jsonify({"message": "Feedback submitted successfully", "feedback_id": feedback_id}), 201
    return jsonify({"message": "Failed to submit feedback"}), 500

@user_bp.route('/statistics', methods=['GET'])
@token_required
def get_user_statistics_route(current_user_id):
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    try:
        total_scans = statistics_model.get_user_total_scans(current_user_id, start_date, end_date)
        if total_scans is None:
            return jsonify({"message": "Failed to retrieve statistics data due to a server error."}), 500
        if total_scans == 0:
            return jsonify({
                "message": "No scans found for the selected period.",
                "total_scans": 0,
                "disease_distribution": {},
                "tree_scan_counts": []
            }), 200
        disease_distribution = statistics_model.get_user_disease_distribution(current_user_id, start_date, end_date)
        tree_scan_counts = statistics_model.get_user_scans_by_tree(current_user_id, start_date, end_date)
        return jsonify({
            "total_scans": total_scans,
            "disease_distribution": disease_distribution,
            "tree_scan_counts": tree_scan_counts
        }), 200
    except Exception as e:
        current_app.logger.error(f"User statistics error: {e}")
        return jsonify({"message": "Failed to retrieve user statistics"}), 500