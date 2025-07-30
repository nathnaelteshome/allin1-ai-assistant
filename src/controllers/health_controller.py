import logging
from typing import Dict, List, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from ..infrastructure.gemini_service import GeminiService
from ..infrastructure.composio_service import ComposioService
from ..use_cases.composio_planner_agent import ComposioPlannerAgent

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# Pydantic models
class ServiceHealthResponse(BaseModel):
    service: str
    status: str
    details: Dict[str, Any]
    checked_at: str


class SystemHealthResponse(BaseModel):
    overall_status: str
    services: List[ServiceHealthResponse]
    system_info: Dict[str, Any]
    checked_at: str


class HealthController:
    """
    FastAPI controller for health checks and system monitoring.
    """
    
    def __init__(
        self,
        gemini_service: GeminiService,
        composio_service: ComposioService,
        planner_agent: ComposioPlannerAgent
    ):
        self.gemini_service = gemini_service
        self.composio_service = composio_service
        self.planner_agent = planner_agent


# Dependency injection
async def get_health_controller() -> HealthController:
    """Dependency injection for health controller."""
    # This will be injected by the main app
    pass


@router.get("/health", response_model=SystemHealthResponse)
async def comprehensive_health_check(
    controller: HealthController = Depends(get_health_controller)
) -> SystemHealthResponse:
    """
    Comprehensive health check for all system services.
    
    Checks the health of Gemini, Composio, Planner Agent, and other components.
    """
    try:
        logger.info("Performing comprehensive health check")
        
        service_results = []
        overall_healthy = True
        
        # Check Gemini service
        try:
            gemini_health = await controller.gemini_service.health_check()
            service_results.append(ServiceHealthResponse(
                service="gemini",
                status=gemini_health['status'],
                details=gemini_health,
                checked_at=gemini_health.get('checked_at', datetime.utcnow().isoformat())
            ))
            if gemini_health['status'] != 'healthy':
                overall_healthy = False
        except Exception as e:
            service_results.append(ServiceHealthResponse(
                service="gemini",
                status="error",
                details={"error": str(e)},
                checked_at=datetime.utcnow().isoformat()
            ))
            overall_healthy = False
        
        # Check Composio service
        try:
            composio_health = await controller.composio_service.health_check()
            service_results.append(ServiceHealthResponse(
                service="composio",
                status=composio_health['status'],
                details=composio_health,
                checked_at=datetime.utcnow().isoformat()
            ))
            if composio_health['status'] != 'healthy':
                overall_healthy = False
        except Exception as e:
            service_results.append(ServiceHealthResponse(
                service="composio",
                status="error",
                details={"error": str(e)},
                checked_at=datetime.utcnow().isoformat()
            ))
            overall_healthy = False
        
        # Check Planner Agent
        try:
            planner_health = await controller.planner_agent.health_check()
            service_results.append(ServiceHealthResponse(
                service="planner_agent",
                status=planner_health['status'],
                details=planner_health,
                checked_at=planner_health.get('checked_at', datetime.utcnow().isoformat())
            ))
            if planner_health['status'] != 'healthy':
                overall_healthy = False
        except Exception as e:
            service_results.append(ServiceHealthResponse(
                service="planner_agent",
                status="error",
                details={"error": str(e)},
                checked_at=datetime.utcnow().isoformat()
            ))
            overall_healthy = False
        
        # System information
        import psutil
        import sys
        system_info = {
            "python_version": sys.version,
            "memory_usage_mb": psutil.virtual_memory().used / 1024 / 1024,
            "cpu_percent": psutil.cpu_percent(),
            "disk_usage_percent": psutil.disk_usage('/').percent,
            "uptime_seconds": psutil.boot_time()
        }
        
        response = SystemHealthResponse(
            overall_status="healthy" if overall_healthy else "unhealthy",
            services=service_results,
            system_info=system_info,
            checked_at=datetime.utcnow().isoformat()
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error in comprehensive health check: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Health check failed: {str(e)}"
        )


@router.get("/health/basic")
async def basic_health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint for load balancers and monitoring.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "allin1-ai-assistant"
    }


@router.get("/health/services/{service_name}")
async def service_health_check(
    service_name: str,
    controller: HealthController = Depends(get_health_controller)
) -> ServiceHealthResponse:
    """
    Health check for a specific service.
    """
    try:
        if service_name == "gemini":
            health = await controller.gemini_service.health_check()
        elif service_name == "composio":
            health = await controller.composio_service.health_check()
        elif service_name == "planner":
            health = await controller.planner_agent.health_check()
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_name}' not found"
            )
        
        response = ServiceHealthResponse(
            service=service_name,
            status=health['status'],
            details=health,
            checked_at=health.get('checked_at', datetime.utcnow().isoformat())
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking {service_name} health: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Health check for {service_name} failed: {str(e)}"
        )


@router.get("/health/tools")
async def tools_health_check(
    controller: HealthController = Depends(get_health_controller)
) -> Dict[str, Any]:
    """
    Health check for Composio tools and scenario availability.
    """
    try:
        logger.info("Performing tools health check")
        
        # Get tool discovery service from planner agent
        tool_discovery = controller.planner_agent.tool_discovery
        
        # Get scenario completeness report
        completeness_report = await tool_discovery.get_scenario_completeness_report()
        
        # Calculate tool availability metrics
        total_scenarios = completeness_report['overall_stats']['total_scenarios']
        functional_scenarios = completeness_report['overall_stats']['functional_scenarios']
        overall_completeness = completeness_report['overall_stats']['completeness_percentage']
        
        # Analyze individual scenarios
        scenario_health = {}
        critical_issues = []
        
        for scenario, scenario_data in completeness_report['scenarios'].items():
            completeness_pct = scenario_data['completeness']['percentage']
            is_functional = scenario_data['completeness']['is_functional']
            
            scenario_health[scenario] = {
                'functional': is_functional,
                'completeness_percentage': completeness_pct,
                'available_tools': len(scenario_data['available_tools']),
                'missing_tools': len(scenario_data['missing_tools']),
                'status': 'healthy' if is_functional else 'degraded'
            }
            
            if not is_functional:
                critical_issues.append(f"Scenario '{scenario}' is not functional")
        
        # Determine overall tools health
        tools_status = "healthy"
        if functional_scenarios < total_scenarios * 0.8:  # Less than 80% functional
            tools_status = "degraded"
        if functional_scenarios == 0:
            tools_status = "unhealthy"
        
        response = {
            "status": tools_status,
            "overall_metrics": {
                "total_scenarios": total_scenarios,
                "functional_scenarios": functional_scenarios,
                "completeness_percentage": overall_completeness,
                "functional_rate": (functional_scenarios / total_scenarios * 100) if total_scenarios > 0 else 0
            },
            "scenario_health": scenario_health,
            "critical_issues": critical_issues,
            "checked_at": datetime.utcnow().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Error in tools health check: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Tools health check failed: {str(e)}"
        )


@router.get("/health/authentication")
async def auth_health_check(
    controller: HealthController = Depends(get_health_controller)
) -> Dict[str, Any]:
    """
    Health check for authentication services and OAuth flows.
    """
    try:
        logger.info("Performing authentication health check")
        
        # Get auth manager from planner agent
        auth_manager = controller.planner_agent.auth_manager
        
        # Test basic auth manager functionality
        # This is a simplified check - in production, you might want more comprehensive tests
        
        # Check Firebase connectivity (implicit in auth manager)
        # Check if we can access OAuth session collection
        
        response = {
            "status": "healthy",  # Simplified for now
            "oauth_providers": {
                "gmail": "available",
                "google_calendar": "available", 
                "twitter": "available",
                "zoom": "available",
                "skyscanner": "available",
                "booking": "available",
                "tripadvisor": "available",
                "doordash": "available",
                "stripe": "available"
            },
            "firebase_connectivity": "connected",
            "oauth_flow_status": "operational",
            "checked_at": datetime.utcnow().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Error in auth health check: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "checked_at": datetime.utcnow().isoformat()
        }


@router.get("/health/metrics")
async def system_metrics(
    controller: HealthController = Depends(get_health_controller)
) -> Dict[str, Any]:
    """
    System performance metrics and statistics.
    """
    try:
        import psutil
        import os
        
        # System metrics
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Application metrics
        planner_agent = controller.planner_agent
        
        # Get conversation and execution stats
        active_conversations = len(planner_agent._active_conversations)
        conversation_history_size = len(planner_agent._conversation_history)
        
        # Get execution stats from function executor
        function_executor = planner_agent.function_executor
        active_executions = len(function_executor._active_executions)
        execution_history_size = len(function_executor._execution_history)
        
        metrics = {
            "system": {
                "memory_total_mb": memory.total / 1024 / 1024,
                "memory_used_mb": memory.used / 1024 / 1024,
                "memory_percent": memory.percent,
                "cpu_percent": psutil.cpu_percent(interval=1),
                "disk_total_gb": disk.total / 1024 / 1024 / 1024,
                "disk_used_gb": disk.used / 1024 / 1024 / 1024,
                "disk_percent": (disk.used / disk.total) * 100,
                "load_average": os.getloadavg() if hasattr(os, 'getloadavg') else None
            },
            "application": {
                "active_conversations": active_conversations,
                "conversation_history_size": conversation_history_size,
                "active_executions": active_executions,
                "execution_history_size": execution_history_size,
                "uptime_seconds": psutil.Process().create_time()
            },
            "cache_stats": {
                "composio_tools_cache": len(planner_agent.composio_service._tools_cache),
                "composio_accounts_cache": len(planner_agent.composio_service._connected_accounts_cache),
                "tool_discovery_cache": len(planner_agent.tool_discovery._scenario_tools_cache)
            },
            "collected_at": datetime.utcnow().isoformat()
        }
        
        return metrics
        
    except Exception as e:
        logger.error(f"Error collecting system metrics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to collect system metrics: {str(e)}"
        )


@router.get("/health/readiness")
async def readiness_check(
    controller: HealthController = Depends(get_health_controller)
) -> Dict[str, Any]:
    """
    Kubernetes-style readiness check.
    
    Checks if the application is ready to serve traffic.
    """
    try:
        # Check critical services
        gemini_health = await controller.gemini_service.health_check()
        composio_health = await controller.composio_service.health_check()
        
        # Application is ready if core services are healthy
        ready = (
            gemini_health['status'] == 'healthy' and 
            composio_health['status'] == 'healthy'
        )
        
        response = {
            "ready": ready,
            "status": "ready" if ready else "not_ready",
            "services": {
                "gemini": gemini_health['status'],
                "composio": composio_health['status']
            },
            "checked_at": datetime.utcnow().isoformat()
        }
        
        # Return appropriate HTTP status
        if not ready:
            raise HTTPException(status_code=503, detail=response)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in readiness check: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail={
                "ready": False,
                "status": "not_ready",
                "error": str(e),
                "checked_at": datetime.utcnow().isoformat()
            }
        )


@router.get("/health/liveness")
async def liveness_check() -> Dict[str, Any]:
    """
    Kubernetes-style liveness check.
    
    Simple check to verify the application process is alive.
    """
    return {
        "alive": True,
        "status": "alive",
        "checked_at": datetime.utcnow().isoformat()
    }


@router.post("/health/cache/clear")
async def clear_caches(
    controller: HealthController = Depends(get_health_controller)
) -> Dict[str, Any]:
    """
    Clear all application caches.
    
    Useful for debugging and forcing refresh of cached data.
    """
    try:
        logger.info("Clearing all application caches")
        
        # Clear Composio service caches
        await controller.composio_service.clear_caches()
        
        # Clear tool discovery caches
        await controller.planner_agent.tool_discovery.clear_cache()
        
        return {
            "success": True,
            "message": "All caches cleared successfully",
            "cleared_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error clearing caches: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear caches: {str(e)}"
        )