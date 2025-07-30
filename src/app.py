import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import our services
from .infrastructure.composio_service import ComposioService
from .infrastructure.composio_auth_manager import ComposioAuthManager
from .infrastructure.composio_tool_discovery import ComposioToolDiscovery
from .infrastructure.composio_function_executor import ComposioFunctionExecutor
from .infrastructure.gemini_service import GeminiService
from .infrastructure.firebase_service import FirebaseService
from .use_cases.composio_planner_agent import ComposioPlannerAgent
from .controllers.composio_task_controller import ComposioTaskController
from .controllers.auth_controller import AuthController
from .controllers.health_controller import HealthController

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Security
security = HTTPBearer()

# Global service instances
services = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown."""
    
    # Startup
    logger.info("Starting Allin1 AI Assistant application...")
    
    try:
        # Initialize Firebase service
        firebase_service = FirebaseService()
        services['firebase'] = firebase_service
        
        # Initialize Gemini service
        gemini_service = GeminiService()
        services['gemini'] = gemini_service
        
        # Initialize Composio services
        composio_service = ComposioService()
        services['composio'] = composio_service
        
        # Initialize authentication manager
        auth_manager = ComposioAuthManager(composio_service, firebase_service)
        services['auth_manager'] = auth_manager
        
        # Initialize tool discovery
        tool_discovery = ComposioToolDiscovery(composio_service)
        services['tool_discovery'] = tool_discovery
        
        # Initialize function executor
        function_executor = ComposioFunctionExecutor(
            composio_service, auth_manager, tool_discovery
        )
        services['function_executor'] = function_executor
        
        # Initialize planner agent
        planner_agent = ComposioPlannerAgent(
            gemini_service, composio_service, auth_manager, 
            tool_discovery, function_executor
        )
        services['planner_agent'] = planner_agent
        
        # Initialize controllers
        services['task_controller'] = ComposioTaskController(
            planner_agent, function_executor, tool_discovery, auth_manager
        )
        services['auth_controller'] = AuthController(auth_manager)
        services['health_controller'] = HealthController(
            gemini_service, composio_service, planner_agent
        )
        
        # Perform health checks
        await perform_startup_health_checks()
        
        # Start background tasks
        asyncio.create_task(cleanup_task())
        
        logger.info("Application startup completed successfully")
        
    except Exception as e:
        logger.error(f"Application startup failed: {str(e)}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Allin1 AI Assistant application...")
    
    try:
        # Cleanup services
        for service_name, service in services.items():
            if hasattr(service, 'cleanup'):
                await service.cleanup()
        
        logger.info("Application shutdown completed")
        
    except Exception as e:
        logger.error(f"Error during application shutdown: {str(e)}")


async def perform_startup_health_checks():
    """Perform health checks on all services during startup."""
    
    logger.info("Performing startup health checks...")
    
    # Check Gemini service
    gemini_health = await services['gemini'].health_check()
    if gemini_health['status'] != 'healthy':
        raise Exception(f"Gemini service unhealthy: {gemini_health.get('error')}")
    
    # Check Composio service
    composio_health = await services['composio'].health_check()
    if composio_health['status'] != 'healthy':
        raise Exception(f"Composio service unhealthy: {composio_health.get('error')}")
    
    # Check planner agent
    planner_health = await services['planner_agent'].health_check()
    if planner_health['status'] != 'healthy':
        raise Exception(f"Planner agent unhealthy: {planner_health.get('error')}")
    
    logger.info("All health checks passed")


async def cleanup_task():
    """Background task for periodic cleanup."""
    
    while True:
        try:
            # Clean up expired conversations
            await services['planner_agent'].cleanup_expired_conversations()
            
            # Clean up expired OAuth sessions
            await services['auth_manager'].cleanup_expired_sessions()
            
            # Wait for 1 hour before next cleanup
            await asyncio.sleep(3600)
            
        except Exception as e:
            logger.error(f"Error in cleanup task: {str(e)}")
            await asyncio.sleep(300)  # Wait 5 minutes on error


# Create FastAPI application
app = FastAPI(
    title="Allin1 AI Assistant",
    description="AI-powered assistant with unified tool execution via Composio and Gemini",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency injection
async def get_firebase_service() -> FirebaseService:
    return services['firebase']


async def get_gemini_service() -> GeminiService:
    return services['gemini']


async def get_composio_service() -> ComposioService:
    return services['composio']


async def get_auth_manager() -> ComposioAuthManager:
    return services['auth_manager']


async def get_tool_discovery() -> ComposioToolDiscovery:
    return services['tool_discovery']


async def get_function_executor() -> ComposioFunctionExecutor:
    return services['function_executor']


async def get_planner_agent() -> ComposioPlannerAgent:
    return services['planner_agent']


async def get_task_controller() -> ComposioTaskController:
    return services['task_controller']


async def get_auth_controller() -> AuthController:
    return services['auth_controller']


async def get_health_controller() -> HealthController:
    return services['health_controller']


# Simple authentication dependency (to be enhanced)
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Simple authentication dependency. 
    In production, this should validate JWT tokens and return user info.
    """
    # For now, return a simple use havr ID extracted from token
    # This should be replaced with proper JWT validation
    token = credentials.credentials
    
    # Simple validation - in production, use proper JWT validation
    if token.startswith("user_"):
        return token
    else:
        raise HTTPException(status_code=401, detail="Invalid authentication token")


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": asyncio.get_event_loop().time()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "status_code": 500,
            "timestamp": asyncio.get_event_loop().time()
        }
    )


# Health check endpoint
@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": asyncio.get_event_loop().time(),
        "message": "Server is running"
    }


# Include routers from controllers
from .controllers.composio_task_controller import router as task_router, get_task_controller
from .controllers.auth_controller import router as auth_router, get_auth_controller
from .controllers.health_controller import router as health_router, get_health_controller

# Override dependency injection for controllers
app.dependency_overrides[get_auth_controller] = lambda: services['auth_controller']
app.dependency_overrides[get_task_controller] = lambda: services['task_controller']
app.dependency_overrides[get_health_controller] = lambda: services['health_controller']

app.include_router(task_router, prefix="/api/v1", tags=["tasks"])
app.include_router(auth_router, prefix="/api/v1", tags=["authentication"])
app.include_router(health_router, prefix="/api/v1", tags=["health"])


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Allin1 AI Assistant",
        "version": "1.0.0",
        "description": "AI-powered assistant with unified tool execution",
        "documentation": "/docs",
        "health": "/health",
        "api_prefix": "/api/v1"
    }


if __name__ == "__main__":
    # Configuration
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("DEBUG", "False").lower() == "true"
    
    # Run the application
    uvicorn.run(
        "src.app:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info" if not debug else "debug"
    )