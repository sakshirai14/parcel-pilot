from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

class TimeService:
    # Dataset snapshot time is 2026-08-16 11:00 Asia/Kolkata
    TIMEZONE = ZoneInfo("Asia/Kolkata")
    SNAPSHOT_TIME = datetime(2026, 8, 16, 11, 0, 0, tzinfo=TIMEZONE)

    @classmethod
    def get_snapshot_time(cls) -> datetime:
        return cls.SNAPSHOT_TIME

    @classmethod
    def parse_timestamp(cls, ts_str: str) -> datetime:
        """
        Parses a timestamp string into a timezone-aware datetime.
        Handles format like '2026-08-16 11:00:00', '2026-08-16T11:00:00Z', '2026-08-16T11:00:00+05:30', etc.
        """
        if not ts_str:
            raise ValueError("Timestamp string cannot be empty.")
            
        # Standardize 'T' and ' ' separation
        ts_str = ts_str.replace("T", " ")
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1]
            
        # Strip timezone offset if present for parsing, but apply correct tz
        # SQLite / Excel dates are generally stored as local strings
        # Example format: '2026-08-16 10:52:00' or '2026-08-16 10:52:00.000000'
        # Split off offset if it's there
        if "+" in ts_str:
            ts_str, _ = ts_str.split("+", 1)
        elif ts_str.count("-") > 2:
            # Handle cases where timezone offset is negative, e.g. 2026-08-16 10:52:00-05:00
            parts = ts_str.rsplit("-", 1)
            ts_str = parts[0]
            
        ts_str = ts_str.strip()
        
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(ts_str, fmt)
                # Assume local Asia/Kolkata timezone if none specified, matching the dataset context
                return dt.replace(tzinfo=cls.TIMEZONE)
            except ValueError:
                continue
                
        raise ValueError(f"Unable to parse timestamp: {ts_str}")

    @classmethod
    def hours_between(cls, start: str, end: str) -> float:
        dt_start = cls.parse_timestamp(start)
        dt_end = cls.parse_timestamp(end)
        diff = dt_end - dt_start
        return diff.total_seconds() / 3600.0

    @classmethod
    def days_between(cls, start: str, end: str) -> float:
        return cls.hours_between(start, end) / 24.0

    @classmethod
    def ticket_age_hours(cls, created_at: str) -> float:
        """
        Calculates the age of a ticket relative to the dataset snapshot time.
        """
        return cls.hours_between(created_at, cls.SNAPSHOT_TIME.strftime("%Y-%m-%d %H:%M:%S"))

    @classmethod
    def pickup_delay_hours(cls, scheduled_window_end: str, actual_pickup: Optional[str]) -> Optional[float]:
        """
        Calculates the delay in pickup. If actual_pickup is not yet recorded, returns the hours
        between the scheduled window end and the snapshot time.
        """
        if not scheduled_window_end:
            return None
            
        end_time = cls.parse_timestamp(scheduled_window_end)
        
        if actual_pickup:
            actual_time = cls.parse_timestamp(actual_pickup)
            diff = actual_time - end_time
            return max(0.0, diff.total_seconds() / 3600.0)
        else:
            # If not picked up yet, compare scheduled window end to snapshot time
            diff = cls.SNAPSHOT_TIME - end_time
            return max(0.0, diff.total_seconds() / 3600.0)
