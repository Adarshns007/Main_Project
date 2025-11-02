# backend/models/statistics_model.py

from backend.services.database_service import DatabaseService
from typing import Optional, Dict
from flask import current_app
from backend.api.geo_utils import haversine_distance 
from datetime import datetime, timedelta
from backend.models.farm_model import FarmModel 

class StatisticsModel:
    """
    Handles aggregation and calculation of user-specific statistics and geo-spatial data.
    """
    
    # Define Disease Severity Index
    SEVERITY_INDEX = {
        'Healthy': 0,
        'Sooty Mould': 1,
        'Powdery Mildew': 2,
        'Gall Midge': 2,
        'Anthracnose': 3,
        'Bacterial Canker': 3,
        'Cutting Weevil': 3,
        'die back': 3,
    }
    
    def __init__(self):
        self.db = DatabaseService()
        self.farm_model = FarmModel()

    def get_user_disease_distribution(self, user_id: int, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict:
        """
        Calculates the distribution of predicted diseases for a specific user within a date range.
        """
        base_query = """
            SELECT 
                p.predicted_class, 
                COUNT(*) AS count
            FROM predictions p
            JOIN images i ON p.image_id = i.image_id
            WHERE i.user_id = %s
        """
        params = [user_id]
        
        if start_date:
            base_query += " AND i.upload_date >= %s"
            params.append(start_date)
        if end_date:
            base_query += " AND i.upload_date <= %s"
            params.append(end_date)
            
        base_query += " GROUP BY p.predicted_class"
        
        results = self.db.execute_query(base_query, tuple(params))
        
        distribution = {row['predicted_class']: row['count'] for row in results} if results else {}
        return distribution

    def get_user_scans_by_tree(self, user_id: int, start_date: Optional[str] = None, end_date: Optional[str] = None) -> list:
        """
        Counts the number of scans per tree owned by the user.
        """
        base_query = """
            SELECT 
                t.tree_name, 
                COUNT(i.image_id) AS count
            FROM images i
            JOIN trees t ON i.tree_id = t.tree_id
            JOIN farms f ON t.farm_id = f.farm_id
            WHERE i.user_id = %s AND i.tree_id IS NOT NULL
        """
        params = [user_id]
        
        if start_date:
            base_query += " AND i.upload_date >= %s"
            params.append(start_date)
        if end_date:
            base_query += " AND i.upload_date <= %s"
            params.append(end_date)
            
        base_query += " GROUP BY t.tree_name ORDER BY count DESC"
        
        results = self.db.execute_query(base_query, tuple(params))
        return results if results else []

    def get_user_total_scans(self, user_id: int, start_date: Optional[str] = None, end_date: Optional[str] = None) -> int:
        """
        Gets the total number of scans for a user within a date range.
        """
        base_query = "SELECT COUNT(*) AS total FROM images WHERE user_id = %s"
        params = [user_id]
        
        if start_date:
            base_query += " AND upload_date >= %s"
            params.append(start_date)
        if end_date:
            base_query += " AND upload_date <= %s"
            params.append(end_date)
            
        result = self.db.execute_query(base_query, tuple(params), fetch_one=True)
        return result['total'] if result and 'total' in result else 0
        
    def get_tree_health_scores(self, tree_id: int) -> list:
        """
        New method to get Disease Index for a tree over time (for Time-Series Chart)
        """
        query = """
            SELECT 
                i.upload_date, 
                p.predicted_class
            FROM images i
            JOIN predictions p ON i.image_id = p.image_id
            WHERE i.tree_id = %s
            ORDER BY i.upload_date ASC
        """
        results = self.db.execute_query(query, (tree_id,))
        
        scores = []
        if results:
            for row in results:
                disease = row['predicted_class']
                scores.append({
                    'date': row['upload_date'].isoformat(),
                    'score': self.SEVERITY_INDEX.get(disease, 0),
                    'disease': disease
                })
        return scores

    def get_regional_disease_data(self, target_latitude: float, target_longitude: float, max_distance_km: float = 5.0) -> Dict:
        """
        Retrieves aggregated, anonymous disease distribution data based on UNIQUE 
        AFFECTED TREES/POINTS within a radius of the target location.
        """
        query = """
            SELECT 
                p.predicted_class, 
                i.tree_id, 
                COALESCE(f.latitude, i.scan_latitude) AS latitude, 
                COALESCE(f.longitude, i.scan_longitude) AS longitude
            FROM images i
            JOIN predictions p ON i.image_id = p.image_id
            LEFT JOIN trees t ON i.tree_id = t.tree_id
            LEFT JOIN farms f ON t.farm_id = f.farm_id
            WHERE p.predicted_class != 'Healthy' 
                AND (f.latitude IS NOT NULL OR i.scan_latitude IS NOT NULL)
        """
        all_diseased_scans = self.db.execute_query(query) or []

        # Key: Disease Name, Value: Set of unique tree_ids affected
        unique_affected_units = {}
        
        # 2. Iterate through all scans, calculate distance, and aggregate
        for scan in all_diseased_scans:
            try:
                scan_lat = float(scan['latitude'])
                scan_lon = float(scan['longitude'])
            except (TypeError, ValueError):
                continue 

            distance = haversine_distance(target_latitude, target_longitude, scan_lat, scan_lon)
            
            if distance <= max_distance_km:
                disease = scan['predicted_class']
                
                # CRITICAL CHANGE: Only count units linked to a Tree (non-null tree_id)
                unit_id = scan['tree_id']
                
                if unit_id is not None:
                    if disease not in unique_affected_units:
                        unique_affected_units[disease] = set()
                    unique_affected_units[disease].add(unit_id)
        
        # Final aggregation: count the size of the set for each disease
        regional_tree_counts = {
            disease: len(unit_ids) 
            for disease, unit_ids in unique_affected_units.items()
        }
        
        return {
            "regional_tree_counts": regional_tree_counts
        }

    def check_geo_outbreak_risk(self, user_id: int, max_distance_km: float = 5.0) -> Dict:
        """
        Checks for outbreak risk by comparing scans within 5km distance.
        """
        # 1. Define current analysis period (Last 7 days) and Baseline period (7-14 days ago)
        current_end = datetime.now()
        current_start = current_end - timedelta(days=7)
        baseline_start = current_end - timedelta(days=14)

        # 2. Filter all scans for the entire system within the last 14 days with coordinates
        query = """
            SELECT 
                p.predicted_class, i.upload_date, 
                COALESCE(f.latitude, i.scan_latitude) AS latitude, 
                COALESCE(f.longitude, i.scan_longitude) AS longitude, 
                f.user_id as farm_user_id
            FROM images i
            JOIN predictions p ON i.image_id = p.image_id
            LEFT JOIN trees t ON i.tree_id = t.tree_id
            LEFT JOIN farms f ON t.farm_id = f.farm_id
            WHERE i.upload_date >= %s AND (f.latitude IS NOT NULL OR i.scan_latitude IS NOT NULL)
        """
        all_scans_14_days = self.db.execute_query(query, (baseline_start,)) or []

        # 3. Get the target farms (the user's farms)
        target_farms = self.farm_model.get_all_user_farms(user_id)
        # Filter to only include farms with coordinates (required for comparison)
        target_farms = [f for f in target_farms if f.get('latitude') and f.get('longitude')]
        
        if not target_farms:
            return {"risk_found": False, "message": "No geo-tagged farms found for this user. Add coordinates to your farms to enable alerts."}

        # 4. Analyze risk for each of the user's farms
        outbreak_data = {}
        for target_farm in target_farms:
            # FIX: Ensure coordinates are float before math calculation
            try:
                target_lat = float(target_farm['latitude'])
                target_lon = float(target_farm['longitude'])
            except (TypeError, ValueError):
                current_app.logger.error(f"Invalid coordinates for target farm {target_farm['farm_id']}")
                continue 
            
            nearby_scans_current = 0
            nearby_diseased_current = 0
            nearby_scans_baseline = 0
            nearby_diseased_baseline = 0
            
            # Aggregate nearby data
            for scan in all_scans_14_days:
                # Skip self-comparison 
                if scan.get('farm_user_id') == user_id:
                     continue
                     
                try:
                    scan_lat = float(scan['latitude'])
                    scan_lon = float(scan['longitude'])
                except (TypeError, ValueError):
                    continue 

                # Check distance
                distance = haversine_distance(target_lat, target_lon, scan_lat, scan_lon)
                
                if distance <= max_distance_km:
                    # Check for disease (severity > 0)
                    is_diseased = self.SEVERITY_INDEX.get(scan['predicted_class'], 0) > 0
                    
                    if scan['upload_date'] >= current_start:
                        # Current period (Last 7 days)
                        nearby_scans_current += 1
                        if is_diseased:
                            nearby_diseased_current += 1
                    else:
                        # Baseline period (7-14 days ago)
                        nearby_scans_baseline += 1
                        if is_diseased:
                            nearby_diseased_baseline += 1

            # 5. Calculate Prevalence and Change Rate
            current_prevalence = (nearby_diseased_current / nearby_scans_current) if nearby_scans_current else 0
            baseline_prevalence = (nearby_diseased_baseline / nearby_scans_baseline) if nearby_scans_baseline else 0
            
            risk_increase = 0
            if baseline_prevalence > 0 and current_prevalence >= 0.10: # Only calculate increase if current is already high enough
                risk_increase = (current_prevalence - baseline_prevalence) / baseline_prevalence 
            
            # Thresholds: Current prevalence > 10% AND increase rate > 20%
            if current_prevalence >= 0.10 and risk_increase >= 0.20:
                outbreak_data[target_farm['farm_name']] = {
                    "current_rate": f"{current_prevalence*100:.1f}%",
                    "baseline_rate": f"{baseline_prevalence*100:.1f}%",
                    "increase_percent": f"{risk_increase*100:.0f}%",
                    "status": "ALERT"
                }

        if outbreak_data:
            return {"risk_found": True, "outbreaks": outbreak_data}
        else:
            return {"risk_found": False, "message": "No significant Geo-Outbreak risk detected in your region."}