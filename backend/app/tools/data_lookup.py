import sqlite3
from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel
from backend.app.config import DATABASE_PATH
from backend.app.security.auth import UserContext
from backend.app.security.permissions import (
    enforce_account_access,
    enforce_order_access,
    enforce_ticket_access,
    AccessDeniedException
)
from backend.app.schemas.operational import AccountData, OrderData, TicketData

class OperationalLookupResult(BaseModel):
    status: str  # "SUCCESS", "UNAUTHORIZED", "NOT_FOUND", "ERROR"
    data: Optional[Any] = None
    message: Optional[str] = None

class DataLookupTool:
    @staticmethod
    def _get_connection():
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    def lookup_account(cls, user_context: UserContext, account_id: str) -> OperationalLookupResult:
        try:
            enforce_account_access(user_context, account_id)
        except AccessDeniedException as e:
            return OperationalLookupResult(status="UNAUTHORIZED", message=str(e))

        conn = cls._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,))
            row = cursor.fetchone()
            if not row:
                return OperationalLookupResult(status="NOT_FOUND", message=f"Account {account_id} not found.")
            
            data = AccountData(**dict(row))
            return OperationalLookupResult(status="SUCCESS", data=data)
        except Exception as e:
            return OperationalLookupResult(status="ERROR", message=str(e))
        finally:
            conn.close()

    @classmethod
    def lookup_order(cls, user_context: UserContext, order_id: str) -> OperationalLookupResult:
        conn = cls._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
            row = cursor.fetchone()
            if not row:
                return OperationalLookupResult(status="NOT_FOUND", message=f"Order {order_id} not found.")
            
            order_dict = dict(row)
            
            # Enforce access using the account_id inside the order
            try:
                enforce_order_access(user_context, order_dict["account_id"])
            except AccessDeniedException as e:
                return OperationalLookupResult(status="UNAUTHORIZED", message=str(e))

            data = OrderData(**order_dict)
            return OperationalLookupResult(status="SUCCESS", data=data)
        except Exception as e:
            return OperationalLookupResult(status="ERROR", message=str(e))
        finally:
            conn.close()

    @classmethod
    def lookup_ticket(cls, user_context: UserContext, ticket_id: str) -> OperationalLookupResult:
        conn = cls._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
            row = cursor.fetchone()
            if not row:
                return OperationalLookupResult(status="NOT_FOUND", message=f"Ticket {ticket_id} not found.")
            
            ticket_dict = dict(row)
            
            # Enforce access using the account_id inside the ticket
            try:
                enforce_ticket_access(user_context, ticket_dict["account_id"])
            except AccessDeniedException as e:
                return OperationalLookupResult(status="UNAUTHORIZED", message=str(e))

            data = TicketData(**ticket_dict)
            return OperationalLookupResult(status="SUCCESS", data=data)
        except Exception as e:
            return OperationalLookupResult(status="ERROR", message=str(e))
        finally:
            conn.close()

    @classmethod
    def get_account_orders(cls, user_context: UserContext, account_id: str) -> OperationalLookupResult:
        try:
            enforce_account_access(user_context, account_id)
        except AccessDeniedException as e:
            return OperationalLookupResult(status="UNAUTHORIZED", message=str(e))

        conn = cls._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE account_id = ?", (account_id,))
            rows = cursor.fetchall()
            
            data = [OrderData(**dict(row)) for row in rows]
            return OperationalLookupResult(status="SUCCESS", data=data)
        except Exception as e:
            return OperationalLookupResult(status="ERROR", message=str(e))
        finally:
            conn.close()

    @classmethod
    def get_account_tickets(cls, user_context: UserContext, account_id: str) -> OperationalLookupResult:
        try:
            enforce_account_access(user_context, account_id)
        except AccessDeniedException as e:
            return OperationalLookupResult(status="UNAUTHORIZED", message=str(e))

        conn = cls._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tickets WHERE account_id = ?", (account_id,))
            rows = cursor.fetchall()
            
            data = [TicketData(**dict(row)) for row in rows]
            return OperationalLookupResult(status="SUCCESS", data=data)
        except Exception as e:
            return OperationalLookupResult(status="ERROR", message=str(e))
        finally:
            conn.close()
