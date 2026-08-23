from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pydantic import BaseModel
from backend.app.services.time_service import TimeService

class SLAResult(BaseModel):
    status: str  # "BREACHED", "NOT_BREACHED", "APPROACHING"
    target_hours: float
    elapsed_hours: float
    remaining_hours: float
    deadline: str
    source: str

class SLAService:
    @staticmethod
    def is_business_hour(dt: datetime) -> bool:
        if dt.weekday() >= 5:  # Weekend
            return False
        return 9 <= dt.hour < 17

    @classmethod
    def add_business_hours(cls, start_dt: datetime, hours: float) -> datetime:
        current_dt = start_dt
        # Move to next business start if outside business hours
        while True:
            if current_dt.weekday() >= 5:
                current_dt = current_dt.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
            elif current_dt.hour >= 17:
                current_dt = current_dt.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
            elif current_dt.hour < 9:
                current_dt = current_dt.replace(hour=9, minute=0, second=0, microsecond=0)
            else:
                break
                
        minutes_left = int(hours * 60)
        while minutes_left > 0:
            end_of_day = current_dt.replace(hour=17, minute=0, second=0, microsecond=0)
            mins_till_end = int((end_of_day - current_dt).total_seconds() / 60)
            
            if mins_till_end >= minutes_left:
                current_dt += timedelta(minutes=minutes_left)
                minutes_left = 0
            else:
                minutes_left -= mins_till_end
                current_dt = end_of_day + timedelta(days=1)
                current_dt = current_dt.replace(hour=9, minute=0, second=0, microsecond=0)
                while current_dt.weekday() >= 5:
                    current_dt += timedelta(days=1)
                    
        return current_dt

    @classmethod
    def business_hours_between(cls, start_dt: datetime, end_dt: datetime) -> float:
        if start_dt >= end_dt:
            return 0.0
            
        # Step through in 5-minute increments for simplicity and precision
        total_mins = 0
        current_dt = start_dt
        step = timedelta(minutes=5)
        
        while current_dt < end_dt:
            if cls.is_business_hour(current_dt):
                total_mins += 5
            current_dt += step
            
        return total_mins / 60.0

    @classmethod
    def calculate_sla(
        cls, 
        created_at_str: str, 
        severity: str, 
        plan: str, 
        account_id: str
    ) -> SLAResult:
        """
        Calculates SLA details for a ticket based on snapshot time.
        """
        created_at = TimeService.parse_timestamp(created_at_str)
        snapshot_time = TimeService.get_snapshot_time()
        
        # Check custom agreements
        target_hours = None
        is_24_7 = False
        source = "Standard Support Policy v3"
        
        if account_id == "ACCT-001":  # Northstar Logistics
            source = "05_Northstar_Logistics_Enterprise_Agreement.pdf"
            if severity == "P1":
                target_hours = 0.25  # 15 mins
                is_24_7 = True
            elif severity == "P2":
                target_hours = 1.0  # 1 hour
                is_24_7 = False  # Support policy doesn't specify P2/P3 as 24/7; assume standard business hours
            elif severity == "P3":
                target_hours = 8.0  # 8 business hours
                is_24_7 = False
                
        elif account_id == "ACCT-002":  # LumenWorks
            source = "06_LumenWorks_Service_Agreement.pdf"
            is_24_7 = False  # Custom terms state "No weekend or after-hours support coverage."
            if severity == "P1":
                target_hours = 2.0
            elif severity == "P2":
                target_hours = 4.0
            elif severity == "P3":
                target_hours = 16.0  # 2 business days (2 * 8 = 16 hours)
                
        else:
            # Default Policies from Support Policy v3
            if plan.upper() == "ENTERPRISE":
                if severity == "P1":
                    target_hours = 0.5  # 30 mins
                    is_24_7 = True
                elif severity == "P2":
                    target_hours = 2.0  # 2 hours
                    is_24_7 = False
                elif severity == "P3":
                    target_hours = 8.0  # 1 business day (8 hours)
                    is_24_7 = False
            elif plan.upper() == "GROWTH":
                is_24_7 = False
                if severity == "P1":
                    target_hours = 2.0  # 2 business hours
                elif severity == "P2":
                    target_hours = 4.0  # 4 business hours
                elif severity == "P3":
                    target_hours = 16.0  # 2 business days (16 hours)
            else:  # Standard
                is_24_7 = False
                if severity == "P1":
                    target_hours = 4.0  # 4 business hours
                elif severity == "P2":
                    target_hours = 8.0  # 1 business day (8 hours)
                elif severity == "P3":
                    target_hours = 16.0  # 2 business days (16 hours)

        # Fallback in case of invalid inputs
        if target_hours is None:
            target_hours = 8.0

        # Calculate deadline
        if is_24_7:
            deadline = created_at + timedelta(hours=target_hours)
            elapsed_hours = (snapshot_time - created_at).total_seconds() / 3600.0
            remaining_hours = (deadline - snapshot_time).total_seconds() / 3600.0
        else:
            deadline = cls.add_business_hours(created_at, target_hours)
            elapsed_hours = cls.business_hours_between(created_at, snapshot_time)
            # For business hours, remaining is target_hours minus elapsed
            remaining_hours = target_hours - elapsed_hours

        # Determine status
        if remaining_hours < 0:
            status = "BREACHED"
        elif remaining_hours <= 1.0:  # Within 1 hour of breach
            status = "APPROACHING"
        else:
            status = "NOT_BREACHED"

        return SLAResult(
            status=status,
            target_hours=round(target_hours, 2),
            elapsed_hours=round(elapsed_hours, 2),
            remaining_hours=round(remaining_hours, 2),
            deadline=deadline.strftime("%Y-%m-%d %H:%M:%S"),
            source=source
        )
