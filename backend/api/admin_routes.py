from flask import Blueprint, request, jsonify, current_app, url_for
from backend.api.user_routes import token_required # Re-use generic token check
from backend.models.admin_model import AdminModel
from functools import wraps
from backend.models.feedback_model import FeedbackModel
from backend.models.disease_model import DiseaseModel
from backend.models.user_model import UserModel # Needed to check user role
from backend.models.image_model import ImageModel 

# Create Blueprint
admin_bp = Blueprint('admin_bp', __name__)
admin_model = None # Initialized to None, injected by app.py later
feedback_model = FeedbackModel()
disease_model = DiseaseModel()
user_model = UserModel() # Initialize UserModel for role lookups
image_model = ImageModel() # FIX: Initialize ImageModel

# --- Admin Authorization Decorator (FIXED) ---
def admin_required(f):
    """Decorator to enforce that the authenticated user has the 'admin' role."""
    @token_required # Ensure token is present and valid first
    @wraps(f)
    def decorated_admin(current_user_id, *args, **kwargs):
        # 1. Look up the user by ID using the validated ID from the token
        user = user_model.find_user_by_id(current_user_id)
        
        # 2. Check if the user exists and has the 'admin' role
        if not user or user.get('role') != 'admin':
            # Unauthorized access (User is logged in, but not an admin)
            return jsonify({'message': 'Authorization failed: Admin access required'}), 403
        
        # Pass user ID along
        kwargs['current_user_id'] = current_user_id
        return f(*args, **kwargs)
    return decorated_admin

# ==============================================================================
# --- Dashboard Metrics Routes (/api/admin/metrics) ---
# ==============================================================================

@admin_bp.route('/metrics', methods=['GET'])
@admin_required
def get_metrics_route(current_user_id):
    """Retrieves high-level statistics and disease distribution for the admin dashboard."""
    
    # CRITICAL FIX: Explicitly check for uninitialized dependency before calling methods
    if admin_model is None:
        current_app.logger.error("AdminModel dependency is not initialized. Returning empty data.")
        # Return a non-200 code to inform the client of a server issue, but include a data structure to avoid client-side crash
        return jsonify({
            "metrics": {},
            "disease_distribution": {},
            "message": "Metrics service is temporarily unavailable (Dependency error)."
        }), 503 

    try:
        metrics = admin_model.get_system_metrics()
        distribution = admin_model.get_disease_distribution()
        
        return jsonify({
            "metrics": metrics,
            "disease_distribution": distribution
        }), 200
    except Exception as e:
        current_app.logger.error(f"Admin metrics error: {e}")
        return jsonify({"message": "Failed to retrieve administration metrics"}), 500

# ==============================================================================
# --- User Management Routes (/api/admin/users) ---
# ==============================================================================

@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_all_users_route(current_user_id):
    """Retrieves a list of all users on the platform."""
    # FIX: Ensure admin_model is available before calling its methods
    if admin_model is None:
         return jsonify({"message": "User management service unavailable"}), 503

    try:
        users = admin_model.get_all_users()
        return jsonify(users), 200
    except Exception as e:
        current_app.logger.error(f"Admin users error: {e}")
        return jsonify({"message": "Failed to retrieve user list"}), 500
    
# ==============================================================================
# --- Scan Management Routes (/api/admin/scans) ---
# ==============================================================================
@admin_bp.route('/scans', methods=['GET'])
@admin_required
def get_all_scans_route(current_user_id):
    """
    Retrieves a list of all analyzed images across all users for admin view, 
    with optional filtering by username and date range.
    """
    
    # --- START OF MODIFICATION: Extract Filter Parameters ---
    username = request.args.get('username', None)
    start_date = request.args.get('start_date', None)
    end_date = request.args.get('end_date', None)
    # --- END OF MODIFICATION ---

    try:
        # Pass filters to the model
        scans = image_model.get_all_system_scans(username, start_date, end_date)
        
        # FIX: Handle case where DB returns None on failure
        if scans is None:
            current_app.logger.error("Database query for all system scans returned None. Returning empty list.")
            scans = []
            
        # Format the image URLs and dates for the frontend
        formatted_scans = []
        for scan in scans:
            # FIX 1: Map new aliases back to expected frontend names
            scan['user_id'] = scan.pop('scan_user_id', None)
            scan['username'] = scan.pop('scan_username', 'N/A')
            scan['status'] = scan.pop('image_status', 'unknown') 
            scan['tree_name'] = scan.pop('scan_tree_name', None) 
            scan['farm_name'] = scan.pop('scan_farm_name', None) 

            # FIX 2: Dynamic URL formatting (safely)
            file_path_db = scan.get('file_path')
            
            if not file_path_db or file_path_db == '#':
                 scan['file_path'] = url_for('serve_uploaded_file', filename='placeholder.png', _external=True) 
            else:
                 filename = file_path_db.split('/')[-1]
                 scan['file_path'] = url_for('serve_uploaded_file', filename=filename, _external=True)
                 
            scan['upload_date'] = scan['upload_date'].isoformat() if scan.get('upload_date') else None
            
            formatted_scans.append(scan)

        return jsonify(formatted_scans), 200
    except Exception as e:
        current_app.logger.error(f"Admin all scans error: Critical exception during data fetching/formatting: {e}")
        return jsonify({"message": f"Server Error (500): Failed to process scan data. Exception: {str(e)}"}), 500


# ==============================================================================
# --- Feedback Management Routes (/api/admin/feedbacks) ---
# ==============================================================================

@admin_bp.route('/feedbacks', methods=['GET'])
@admin_required
def get_all_feedbacks_route(current_user_id):
    """Retrieves all feedback records with associated user information."""
    try:
        feedbacks = feedback_model.get_all_feedbacks()
        
        # Convert datetime objects to string format for JSON serialization
        for feedback in feedbacks:
            if feedback.get('submitted_at'):
                # Convert to string and remove timezone for simplicity in JS
                feedback['submitted_at'] = feedback['submitted_at'].isoformat().split('.')[0]
                
        return jsonify(feedbacks), 200
    except Exception as e:
        current_app.logger.error(f"Admin feedbacks error: {e}")
        return jsonify({"message": "Failed to retrieve feedback list"}), 500

@admin_bp.route('/feedbacks/<int:feedback_id>', methods=['PUT'])
@admin_required
def update_feedback_status_route(feedback_id, current_user_id):
    """Updates the status of a specific feedback item."""
    data = request.get_json()
    new_status = data.get('status')
    
    if new_status not in ['new', 'in_review', 'resolved']:
        return jsonify({"message": "Invalid status value"}), 400
        
    if feedback_model.update_feedback_status(feedback_id, new_status):
        return jsonify({"message": f"Feedback {feedback_id} status updated to {new_status}"}), 200
    return jsonify({"message": "Failed to update feedback status"}), 500

# ==============================================================================
# --- Disease Management Routes (/api/admin/diseases) ---
# ==============================================================================

@admin_bp.route('/diseases', methods=['GET'])
@admin_required
def get_all_diseases_route(current_user_id):
    """Retrieves all disease records for the admin view."""
    try:
        diseases = disease_model.get_all_diseases()
        return jsonify(diseases), 200
    except Exception as e:
        current_app.logger.error(f"Admin diseases error: {e}")
        return jsonify({"message": "Failed to retrieve disease list"}), 500

@admin_bp.route('/diseases/<int:disease_id>', methods=['PUT'])
@admin_required
def update_disease_route(disease_id, current_user_id):
    """Updates the description and treatment for a disease."""
    data = request.get_json()
    description = data.get('description')
    organic_treatment = data.get('organic_treatment')
    chemical_treatment = data.get('chemical_treatment')
    
    # FIX CONFIRMED: Checks all three treatment fields now
    if not all([description, organic_treatment, chemical_treatment]):
        return jsonify({"message": "Description, organic treatment, and chemical treatment are required"}), 400

    # FIX CONFIRMED: Passes all three treatment fields to the model
    if disease_model.update_disease(disease_id, description, organic_treatment, chemical_treatment):
        return jsonify({"message": "Disease information updated successfully"}), 200
    return jsonify({"message": "Failed to update disease information or disease not found"}), 500