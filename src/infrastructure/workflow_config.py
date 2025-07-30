"""
Workflow Configuration Service
Centralizes all configuration management following DRY and SOLID principles.
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class TimeoutConfig:
    """Configuration for various timeout operations."""
    composio_apps_fetch: int = 30
    composio_actions_fetch: int = 20
    composio_schema_fetch: int = 15
    composio_auth_check: int = 10
    composio_oauth_init: int = 15
    action_execution: int = 30


@dataclass
class DisplayConfig:
    """Configuration for result display formatting."""
    max_apps_shown: int = 20
    max_actions_shown: int = 15
    max_data_length: int = 3000
    max_raw_display_length: int = 500
    max_items_in_list: int = 5
    max_dict_keys_shown: int = 10


@dataclass
class AppConfig:
    """Configuration for supported apps and their mappings."""
    supported_apps: List[str]
    app_enum_mapping: Dict[str, str]
    fallback_apps: List[str]


@dataclass
class WorkflowConfig:
    """Main configuration class following Single Responsibility Principle."""
    
    def __init__(self):
        self.entity_id = os.getenv('COMPOSIO_ENTITY_ID', 'default')
        self.redirect_url = os.getenv('OAUTH_REDIRECT_URL', 'http://localhost:8000/auth/callback')
        
        # Timeout configurations
        self.timeouts = TimeoutConfig(
            composio_apps_fetch=int(os.getenv('COMPOSIO_APPS_FETCH_TIMEOUT', '30')),
            composio_actions_fetch=int(os.getenv('COMPOSIO_ACTIONS_FETCH_TIMEOUT', '20')),
            composio_schema_fetch=int(os.getenv('COMPOSIO_SCHEMA_FETCH_TIMEOUT', '15')),
            composio_auth_check=int(os.getenv('COMPOSIO_AUTH_CHECK_TIMEOUT', '10')),
            composio_oauth_init=int(os.getenv('COMPOSIO_OAUTH_INIT_TIMEOUT', '15')),
            action_execution=int(os.getenv('COMPOSIO_ACTION_EXECUTION_TIMEOUT', '30'))
        )
        
        # Display configurations
        self.display = DisplayConfig(
            max_apps_shown=int(os.getenv('MAX_APPS_SHOWN', '20')),
            max_actions_shown=int(os.getenv('MAX_ACTIONS_SHOWN', '15')),
            max_data_length=int(os.getenv('MAX_DATA_LENGTH', '3000')),
            max_raw_display_length=int(os.getenv('MAX_RAW_DISPLAY_LENGTH', '500')),
            max_items_in_list=int(os.getenv('MAX_ITEMS_IN_LIST', '5')),
            max_dict_keys_shown=int(os.getenv('MAX_DICT_KEYS_SHOWN', '10'))
        )
        
        # App configurations
        self.app = AppConfig(
            supported_apps=self._get_supported_apps(),
            app_enum_mapping=self._get_app_enum_mapping(),
            fallback_apps=self._get_fallback_apps()
        )
        
        # Sample queries for testing
        self.sample_queries = self._get_sample_queries()
        
        # Workflow step configuration
        self.workflow_steps = self._get_workflow_steps()
    
    def _get_supported_apps(self) -> List[str]:
        """Get list of supported apps from environment or defaults."""
        default_apps = ['GMAIL', 'GITHUB', 'SLACK', 'GOOGLECALENDAR', 'NOTION', 'TWITTER', 'LINKEDIN']
        apps_str = os.getenv('SUPPORTED_APPS', ','.join(default_apps))
        return [app.strip().upper() for app in apps_str.split(',')]
    
    def _get_app_enum_mapping(self) -> Dict[str, str]:
        """Get mapping of app names to Composio App enum values."""
        return {
            'GMAIL': 'GMAIL',
            'GITHUB': 'GITHUB', 
            'SLACK': 'SLACK',
            'CALENDAR': 'GOOGLECALENDAR',
            'GOOGLECALENDAR': 'GOOGLECALENDAR',
            'GOOGLE_CALENDAR': 'GOOGLECALENDAR',
            'NOTION': 'NOTION',
            'TWITTER': 'TWITTER',
            'X': 'TWITTER',
            'LINKEDIN': 'LINKEDIN'
        }
    
    def _get_fallback_apps(self) -> List[str]:
        """Get fallback app list when Composio API is unavailable."""
        return [
            "GMAIL", "GITHUB", "SLACK", "CALENDAR", "DRIVE", "SHEETS", 
            "DOCS", "LINKEDIN", "TWITTER", "DROPBOX", "NOTION", "TRELLO",
            "ASANA", "JIRA", "DISCORD", "ZOOM", "FIGMA", "HUBSPOT"
        ]
    
    def _get_sample_queries(self) -> List[str]:
        """Get sample queries for testing."""
        return [
            "Send an email to test@example.com saying hello world",
            "Fetch my recent 5 emails from Gmail inbox", 
            "Get my GitHub profile information",
            "List my GitHub repositories",
            "Create an issue in my repository with title 'Test Issue'",
            "Schedule a meeting for tomorrow at 2 PM",
            "Post a message to Slack channel",
            "Create a new document in Google Drive"
        ]
    
    def _get_workflow_steps(self) -> List[Dict[str, str]]:
        """Get workflow step definitions."""
        return [
            {"number": "1", "name": "Fetch Composio Apps"},
            {"number": "2", "name": "LLM Selects App"}, 
            {"number": "2.5", "name": "Check Authentication & OAuth"},
            {"number": "3", "name": "Fetch Composio Actions"},
            {"number": "4", "name": "LLM Selects Action"},
            {"number": "5", "name": "Fetch Action Schema"},
            {"number": "6", "name": "LLM Normalizes Parameters"},
            {"number": "7", "name": "Execute Action"}
        ]
    
    def get_app_enum(self, app_name: str) -> Optional[str]:
        """Get Composio App enum for given app name."""
        return self.app.app_enum_mapping.get(app_name.upper())
    
    def is_app_supported(self, app_name: str) -> bool:
        """Check if app is supported."""
        return app_name.upper() in self.app.supported_apps
    
    def validate_config(self) -> Dict[str, bool]:
        """Validate configuration settings."""
        validation = {
            'entity_id_set': bool(self.entity_id),
            'redirect_url_set': bool(self.redirect_url),
            'timeouts_positive': all(
                getattr(self.timeouts, attr) > 0 
                for attr in ['composio_apps_fetch', 'composio_actions_fetch', 'composio_schema_fetch']
            ),
            'display_limits_positive': all(
                getattr(self.display, attr) > 0 
                for attr in ['max_apps_shown', 'max_actions_shown', 'max_data_length']
            ),
            'supported_apps_exist': len(self.app.supported_apps) > 0
        }
        return validation