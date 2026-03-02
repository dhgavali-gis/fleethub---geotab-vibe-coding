from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict, Callable
import mygeotab
import googlemaps
from services.memory_manager import MemoryManager
from services.duckdb_manager import DuckDBManager
from services.traffic_service import TrafficService

@dataclass
class SystemDeps:
    geotab_api: mygeotab.API
    gmp_client: Optional[googlemaps.Client]
    duckdb_manager: DuckDBManager
    memory_manager: MemoryManager
    traffic_service: TrafficService
    current_date: str
    map_commands: List[Dict[str, Any]] = field(default_factory=list)
    on_log: Optional[Callable[[Dict[str, Any]], None]] = None
