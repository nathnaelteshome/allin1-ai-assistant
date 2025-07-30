"""
Result Formatter Service
Handles intelligent formatting of Composio execution results using LLM.
Follows Single Responsibility Principle - only responsible for result formatting.
"""

import logging
from typing import Any, Optional
from abc import ABC, abstractmethod

from .workflow_config import WorkflowConfig

logger = logging.getLogger(__name__)


class ResultFormatterInterface(ABC):
    """Interface for result formatters following Interface Segregation Principle."""
    
    @abstractmethod
    async def format_result(self, data: Any, action_name: str, app_name: str) -> str:
        """Format execution results for display."""
        pass


class LLMResultFormatter(ResultFormatterInterface):
    """LLM-powered result formatter."""
    
    def __init__(self, llm_service, config: WorkflowConfig):
        self.llm_service = llm_service
        self.config = config
        logger.info("LLMResultFormatter initialized")
    
    async def format_result(self, data: Any, action_name: str, app_name: str = "") -> str:
        """Format results using LLM intelligence."""
        try:
            if not data:
                return self._format_empty_result()
            
            # Prepare data for LLM analysis
            data_str = self._prepare_data_for_llm(data)
            
            # Create formatting prompt
            prompt = self._create_formatting_prompt(data_str, action_name, app_name)
            
            # Get formatted result from LLM
            formatted_result = await self.llm_service.gemini_service._generate_response(prompt)
            
            if formatted_result:
                return formatted_result
            else:
                logger.warning("LLM formatting returned empty result, falling back to raw display")
                return self._format_raw_fallback(data)
                
        except Exception as e:
            logger.error(f"LLM formatting error: {str(e)}")
            return self._format_error_fallback(data, str(e))
    
    def _prepare_data_for_llm(self, data: Any) -> str:
        """Prepare data for LLM analysis with size limits."""
        data_str = str(data)
        if len(data_str) > self.config.display.max_data_length:
            data_str = data_str[:self.config.display.max_data_length] + "... [truncated]"
        return data_str
    
    def _create_formatting_prompt(self, data_str: str, action_name: str, app_name: str) -> str:
        """Create prompt for LLM formatting."""
        return f"""
You are helping format API execution results for the user.

App: {app_name}
Action executed: {action_name}
Raw API response data: {data_str}

Please format this data in a clean, user-friendly way. Follow these guidelines:
1. Use emojis and clear headings to organize the information
2. Highlight the most important/relevant information first
3. If it's a list of items (like repositories, emails, etc.), show the first few with key details
4. Explain what the data means in simple terms
5. Keep the formatting concise but informative
6. Use proper indentation and bullets for readability
7. If the data contains personal information, present it respectfully
8. Focus on actionable insights the user can take from this data

Format the response as if you're showing results to a user who just executed this action.
"""
    
    def _format_empty_result(self) -> str:
        """Format empty result message."""
        return """📭 No data returned from API

💡 This could mean:
   • No results found for the search query
   • API returned empty response
   • Authentication/permission issues
   • The action completed successfully but has no return data"""
    
    def _format_raw_fallback(self, data: Any) -> str:
        """Fallback formatting for raw data."""
        return f"⚠️ LLM formatting failed, showing raw data:\n{self._format_simple_data(data)}"
    
    def _format_error_fallback(self, data: Any, error: str) -> str:
        """Fallback formatting when LLM fails."""
        return f"""⚠️ LLM formatting error: {error}
📄 Showing raw data instead:
{self._format_simple_data(data)}"""
    
    def _format_simple_data(self, data: Any) -> str:
        """Simple fallback data formatting."""
        if isinstance(data, dict):
            keys = list(data.keys())
            result = f"📊 Dictionary with {len(data)} keys: {keys}\n"
            
            for key, value in list(data.items())[:self.config.display.max_dict_keys_shown]:
                value_str = str(value)
                if len(value_str) > 100:
                    value_str = value_str[:100] + "..."
                result += f"   • {key}: {value_str}\n"
            
            if len(data) > self.config.display.max_dict_keys_shown:
                result += f"   ... and {len(data) - self.config.display.max_dict_keys_shown} more keys\n"
            
            return result
            
        elif isinstance(data, list):
            result = f"📊 List with {len(data)} items\n"
            
            for i, item in enumerate(data[:self.config.display.max_items_in_list]):
                item_str = str(item)
                if len(item_str) > 100:
                    item_str = item_str[:100] + "..."
                result += f"   [{i}]: {item_str}\n"
            
            if len(data) > self.config.display.max_items_in_list:
                result += f"   ... and {len(data) - self.config.display.max_items_in_list} more items\n"
            
            return result
        else:
            data_str = str(data)
            if len(data_str) > self.config.display.max_raw_display_length:
                data_str = data_str[:self.config.display.max_raw_display_length] + "..."
            return f"📄 {type(data).__name__}: {data_str}"


class SimpleResultFormatter(ResultFormatterInterface):
    """Simple text-based result formatter as fallback."""
    
    def __init__(self, config: WorkflowConfig):
        self.config = config
        logger.info("SimpleResultFormatter initialized")
    
    async def format_result(self, data: Any, action_name: str, app_name: str = "") -> str:
        """Simple formatting without LLM."""
        if not data:
            return "📭 No data returned from API"
        
        if isinstance(data, dict):
            return self._format_dict(data)
        elif isinstance(data, list):
            return self._format_list(data)
        else:
            return f"📄 Result: {str(data)[:self.config.display.max_raw_display_length]}"
    
    def _format_dict(self, data: dict) -> str:
        """Format dictionary data."""
        result = f"📊 Dictionary with {len(data)} keys:\n"
        for key, value in list(data.items())[:self.config.display.max_dict_keys_shown]:
            value_str = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
            result += f"   • {key}: {value_str}\n"
        return result
    
    def _format_list(self, data: list) -> str:
        """Format list data."""
        result = f"📊 List with {len(data)} items:\n"
        for i, item in enumerate(data[:self.config.display.max_items_in_list]):
            item_str = str(item)[:100] + "..." if len(str(item)) > 100 else str(item)
            result += f"   [{i}]: {item_str}\n"
        return result


class ResultFormatterFactory:
    """Factory for creating result formatters following Factory Pattern."""
    
    @staticmethod
    def create_formatter(formatter_type: str, llm_service=None, config: WorkflowConfig = None) -> ResultFormatterInterface:
        """Create appropriate result formatter."""
        if config is None:
            config = WorkflowConfig()
        
        if formatter_type.lower() == 'llm' and llm_service:
            return LLMResultFormatter(llm_service, config)
        elif formatter_type.lower() == 'simple':
            return SimpleResultFormatter(config)
        else:
            logger.warning(f"Unknown formatter type: {formatter_type}, using simple formatter")
            return SimpleResultFormatter(config)