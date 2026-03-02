
from services.mcp_service import mcp_service
from datetime import datetime, timedelta

class DashboardService:
    def __init__(self):
        # Reuse the singleton DuckDB manager from MCP service to access preloaded data
        self.db = mcp_service.duckdb_manager

    def get_kpi_stats(self, days: int = 7):
        """
        Get aggregated KPI stats for the dashboard.
        Args:
            days: Timeframe in days (1, 7, 30)
        """
        try:
            # Calculate start date for filtering
            # DuckDB SQL: CURRENT_DATE - INTERVAL 'X' DAY
            
            # 1. Total Vehicles (Static)
            df_dev, _ = self.db.query("SELECT COUNT(*) as count FROM devices")
            total_vehicles = int(df_dev['count'][0]) if not df_dev.empty else 0
            
            # 2. Active Vehicles (Last 24h logs - Static for now or based on days?)
            # Usually 'Active' means currently active, so 24h is good standard.
            df_active, _ = self.db.query("""
                SELECT COUNT(DISTINCT device_id) as count 
                FROM logs 
                WHERE dateTime >= (CURRENT_TIMESTAMP - INTERVAL 24 HOUR)
            """)
            active_vehicles = int(df_active['count'][0]) if not df_active.empty else 0
            
            # 3. Total Logs (Static count of all logs)
            df_logs, _ = self.db.query("SELECT COUNT(*) as count FROM logs")
            total_logs = int(df_logs['count'][0]) if not df_logs.empty else 0
            
            # 4. Total Violations (Filtered by days)
            df_events, _ = self.db.query(f"""
                SELECT COUNT(*) as count 
                FROM events
                WHERE activeFrom >= (CURRENT_DATE - INTERVAL {days} DAY)
            """)
            total_violations = int(df_events['count'][0]) if not df_events.empty else 0
            
            # 5. Trend Data (Violations by Day - Filtered)
            df_trend, _ = self.db.query(f"""
                SELECT 
                    CAST(activeFrom AS DATE) as date,
                    COUNT(*) as count
                FROM events
                WHERE activeFrom >= (CURRENT_DATE - INTERVAL {days} DAY)
                GROUP BY date
                ORDER BY date
            """)
            trend_data = df_trend.to_dict('records') if not df_trend.empty else []
            
            # 6. Violation Breakdown (Filtered)
            # Remove LIMIT 5 to show all types including Harsh Braking
            df_breakdown, _ = self.db.query(f"""
                SELECT 
                    r.name as rule_name,
                    COUNT(*) as count
                FROM events e
                JOIN rules r ON e.rule_id = r.id
                WHERE e.activeFrom >= (CURRENT_DATE - INTERVAL {days} DAY)
                GROUP BY rule_name
                ORDER BY count DESC
            """)
            breakdown_data = df_breakdown.to_dict('records') if not df_breakdown.empty else []

            return {
                "kpi": {
                    "total_vehicles": total_vehicles,
                    "active_vehicles": active_vehicles,
                    "total_logs": total_logs,
                    "total_violations": total_violations
                },
                "trend": trend_data,
                "breakdown": breakdown_data
            }
            
        except Exception as e:
            print(f"Dashboard Service Error: {e}")
            return {}

dashboard_service = DashboardService()
