import os
import json
import asyncio
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime, timedelta
import logging
import re
from dataclasses import dataclass
from enum import Enum

from .gemini_service import GeminiService
from .composio_service import ComposioService
from .composio_tool_discovery import ComposioToolDiscovery

# Import Composio directly for schema discovery
try:
    from composio import ComposioToolSet, Action
    COMPOSIO_AVAILABLE = True
except ImportError:
    COMPOSIO_AVAILABLE = False

logger = logging.getLogger(__name__)


class ParameterType(Enum):
    """Standard parameter types for tool actions."""
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    DATE = "date"
    EMAIL = "email"
    URL = "url"
    FILE = "file"


@dataclass
class ParameterSpec:
    """Specification for a tool parameter."""
    name: str
    type: ParameterType
    description: str
    required: bool = False
    default: Any = None
    enum_values: Optional[List[str]] = None
    pattern: Optional[str] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    examples: Optional[List[str]] = None
    depends_on: Optional[List[str]] = None


class ComposioParameterGenerator:
    """
    Intelligent parameter generation system that uses LLM to convert natural language
    into structured parameters for Composio tool execution.
    """
    
    def __init__(
        self,
        gemini_service: GeminiService,
        composio_service: ComposioService,
        tool_discovery: ComposioToolDiscovery
    ):
        self.gemini_service = gemini_service
        self.composio_service = composio_service
        self.tool_discovery = tool_discovery
        
        # Parameter generation caches
        self._schema_cache: Dict[str, Dict[str, Any]] = {}
        self._pattern_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._generation_history: List[Dict[str, Any]] = []
        
        # Common parameter patterns for different apps
        self.APP_PARAMETER_PATTERNS = {
            'gmail': {
                'send_email': {
                    'to': {'type': 'email', 'required': True, 'examples': ['user@example.com']},
                    'subject': {'type': 'string', 'required': True, 'examples': ['Meeting tomorrow', 'Project update']},
                    'body': {'type': 'string', 'required': True, 'examples': ['Hello, how are you?']},
                    'cc': {'type': 'array', 'items': 'email', 'required': False},
                    'bcc': {'type': 'array', 'items': 'email', 'required': False}
                },
                'fetch_emails': {
                    'q': {'type': 'string', 'required': False, 'examples': ['is:unread', 'from:sender@example.com']},
                    'max_results': {'type': 'integer', 'default': 10, 'min': 1, 'max': 100},
                    'include_spam_trash': {'type': 'boolean', 'default': False}
                }
            },
            'twitter': {
                'create_post': {
                    'text': {'type': 'string', 'required': True, 'max_length': 280},
                    'media_ids': {'type': 'array', 'items': 'string', 'required': False},
                    'in_reply_to_status_id': {'type': 'string', 'required': False}
                }
            },
            'github': {
                'create_issue': {
                    'title': {'type': 'string', 'required': True},
                    'body': {'type': 'string', 'required': False},
                    'assignees': {'type': 'array', 'items': 'string', 'required': False},
                    'labels': {'type': 'array', 'items': 'string', 'required': False}
                },
                'create_repository': {
                    'name': {'type': 'string', 'required': True},
                    'description': {'type': 'string', 'required': False},
                    'private': {'type': 'boolean', 'default': False},
                    'auto_init': {'type': 'boolean', 'default': True}
                }
            },
            'slack': {
                'send_message': {
                    'channel': {'type': 'string', 'required': True, 'examples': ['#general', '@username']},
                    'text': {'type': 'string', 'required': True},
                    'attachments': {'type': 'array', 'required': False}
                }
            },
            'google_calendar': {
                'create_event': {
                    'summary': {'type': 'string', 'required': True},
                    'start_time': {'type': 'date', 'required': True},
                    'end_time': {'type': 'date', 'required': True},
                    'description': {'type': 'string', 'required': False},
                    'attendees': {'type': 'array', 'items': 'email', 'required': False}
                }
            }
        }
        
        logger.info("ComposioParameterGenerator initialized")

    async def generate_parameters_from_text(
        self,
        user_input: str,
        app_name: str,
        action_name: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate structured parameters from natural language input.
        
        Args:
            user_input: Natural language description of what the user wants to do
            app_name: Target application (gmail, twitter, etc.)
            action_name: Specific action to perform
            context: Additional context for parameter generation
            
        Returns:
            Generated parameters dictionary
        """
        try:
            logger.info(f"Generating parameters for {app_name}.{action_name} from: {user_input[:100]}...")
            
            # Get tool schema for parameter validation
            tool_slug = f"{app_name.upper()}_{action_name.upper()}"
            tool_schema = await self._get_tool_schema(tool_slug)
            
            # Use LLM to extract parameters from natural language
            llm_result = await self._extract_parameters_with_llm(
                user_input, app_name, action_name, tool_schema, context
            )
            
            # Apply app-specific parameter patterns and validation
            enhanced_params = await self._enhance_with_patterns(
                llm_result, app_name, action_name, tool_schema
            )
            
            # Validate and clean parameters
            validated_params = await self._validate_parameters(
                enhanced_params, tool_schema
            )
            
            # Store generation history for learning
            await self._store_generation_history(
                user_input, app_name, action_name, validated_params
            )
            
            logger.info(f"Successfully generated {len(validated_params)} parameters")
            return validated_params
            
        except Exception as e:
            logger.error(f"Error generating parameters: {str(e)}")
            raise

    async def get_parameter_suggestions(
        self,
        app_name: str,
        action_name: str,
        partial_input: str = "",
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get intelligent parameter suggestions for an action.
        
        Args:
            app_name: Target application
            action_name: Specific action
            partial_input: Partial user input for context
            context: Additional context
            
        Returns:
            List of parameter suggestions with examples
        """
        try:
            tool_slug = f"{app_name.upper()}_{action_name.upper()}"
            tool_schema = await self._get_tool_schema(tool_slug)
            
            suggestions = []
            
            # Get app-specific patterns
            app_patterns = self.APP_PARAMETER_PATTERNS.get(app_name, {})
            action_patterns = app_patterns.get(action_name, {})
            
            # Generate suggestions for each required parameter
            required_params = tool_schema.get('required_parameters', [])
            all_params = tool_schema.get('parameters', {})
            
            for param_name in required_params:
                if param_name in all_params:
                    param_info = all_params[param_name]
                    pattern_info = action_patterns.get(param_name, {})
                    
                    suggestion = {
                        'name': param_name,
                        'type': param_info.get('type', 'string'),
                        'description': param_info.get('description', f'Parameter: {param_name}'),
                        'required': True,
                        'examples': pattern_info.get('examples', []),
                        'suggestions': await self._generate_parameter_suggestions(
                            param_name, param_info, partial_input, context
                        )
                    }
                    suggestions.append(suggestion)
            
            # Add optional parameters with high utility
            optional_params = set(all_params.keys()) - set(required_params)
            for param_name in list(optional_params)[:3]:  # Limit to top 3 optional
                param_info = all_params[param_name]
                pattern_info = action_patterns.get(param_name, {})
                
                suggestion = {
                    'name': param_name,
                    'type': param_info.get('type', 'string'),
                    'description': param_info.get('description', f'Parameter: {param_name}'),
                    'required': False,
                    'examples': pattern_info.get('examples', []),
                    'suggestions': await self._generate_parameter_suggestions(
                        param_name, param_info, partial_input, context
                    )
                }
                suggestions.append(suggestion)
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting parameter suggestions: {str(e)}")
            return []

    async def validate_and_complete_parameters(
        self,
        parameters: Dict[str, Any],
        app_name: str,
        action_name: str,
        auto_complete: bool = True
    ) -> Dict[str, Any]:
        """
        Validate parameters and optionally auto-complete missing ones.
        
        Args:
            parameters: Parameters to validate
            app_name: Target application
            action_name: Specific action
            auto_complete: Whether to auto-complete missing parameters
            
        Returns:
            Validated and possibly completed parameters
        """
        try:
            tool_slug = f"{app_name.upper()}_{action_name.upper()}"
            tool_schema = await self._get_tool_schema(tool_slug)
            
            # Validate existing parameters
            validation_result = await self._validate_parameters(parameters, tool_schema)
            
            if not auto_complete:
                return validation_result
            
            # Auto-complete missing required parameters
            required_params = set(tool_schema.get('required_parameters', []))
            provided_params = set(validation_result.keys())
            missing_params = required_params - provided_params
            
            if missing_params:
                logger.info(f"Auto-completing {len(missing_params)} missing parameters")
                
                for param_name in missing_params:
                    param_info = tool_schema.get('parameters', {}).get(param_name, {})
                    default_value = await self._generate_default_parameter_value(
                        param_name, param_info, app_name, action_name
                    )
                    
                    if default_value is not None:
                        validation_result[param_name] = default_value
                        logger.info(f"Auto-completed parameter '{param_name}' with: {default_value}")
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error validating/completing parameters: {str(e)}")
            raise

    async def analyze_parameter_patterns(
        self,
        app_name: str,
        action_name: str,
        sample_inputs: List[str]
    ) -> Dict[str, Any]:
        """
        Analyze patterns in user inputs to improve parameter generation.
        
        Args:
            app_name: Target application
            action_name: Specific action
            sample_inputs: Sample user inputs for analysis
            
        Returns:
            Pattern analysis results
        """
        try:
            patterns = {
                'common_phrases': {},
                'parameter_mappings': {},
                'success_rate': 0,
                'recommendations': []
            }
            
            # Analyze each sample input
            successful_generations = 0
            for input_text in sample_inputs:
                try:
                    generated_params = await self.generate_parameters_from_text(
                        input_text, app_name, action_name
                    )
                    
                    if generated_params:
                        successful_generations += 1
                        
                        # Extract common phrases
                        words = input_text.lower().split()
                        for word in words:
                            if len(word) > 3:  # Skip short words
                                patterns['common_phrases'][word] = patterns['common_phrases'].get(word, 0) + 1
                        
                        # Map phrases to parameters
                        for param_name, param_value in generated_params.items():
                            if param_name not in patterns['parameter_mappings']:
                                patterns['parameter_mappings'][param_name] = []
                            patterns['parameter_mappings'][param_name].append({
                                'input': input_text,
                                'value': param_value
                            })
                            
                except Exception as e:
                    logger.warning(f"Failed to analyze input '{input_text}': {str(e)}")
                    continue
            
            patterns['success_rate'] = successful_generations / len(sample_inputs) if sample_inputs else 0
            
            # Generate recommendations
            if patterns['success_rate'] < 0.7:
                patterns['recommendations'].append(
                    "Consider providing more specific examples in user input"
                )
            
            if len(patterns['common_phrases']) < 5:
                patterns['recommendations'].append(
                    "Input samples may be too generic or repetitive"
                )
            
            return patterns
            
        except Exception as e:
            logger.error(f"Error analyzing parameter patterns: {str(e)}")
            return {'error': str(e)}

    async def _extract_parameters_with_llm(
        self,
        user_input: str,
        app_name: str,
        action_name: str,
        tool_schema: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Extract parameters using LLM with structured prompting."""
        
        # Build comprehensive prompt for parameter extraction
        prompt = f"""
        Extract structured parameters from the user's natural language request for the {app_name} {action_name} action.

        USER REQUEST: "{user_input}"

        AVAILABLE PARAMETERS:
        {json.dumps(tool_schema.get('parameters', {}), indent=2)}

        REQUIRED PARAMETERS: {tool_schema.get('required_parameters', [])}

        CONTEXT: {json.dumps(context or {}, indent=2)}

        INSTRUCTIONS:
        1. Extract all relevant parameters from the user request
        2. Convert natural language to appropriate data types
        3. Use parameter descriptions to understand what each field should contain
        4. For dates, use ISO format (YYYY-MM-DDTHH:MM:SS)
        5. For emails, extract from natural language or use context
        6. For arrays, provide comma-separated values as arrays
        7. Be intelligent about inferring missing information from context

        EXAMPLES FOR {app_name.upper()}:
        - "send email to john@example.com about meeting" → {{"to": "john@example.com", "subject": "about meeting"}}
        - "post tweet saying hello world" → {{"text": "hello world"}}
        - "create GitHub issue for bug in login" → {{"title": "bug in login", "body": "Issue with login functionality"}}

        Return ONLY a valid JSON object with the extracted parameters. Do not include any explanation.
        """
        
        try:
            # Use Gemini service's generate_tool_parameters method
            llm_result = await self.gemini_service.generate_tool_parameters(
                tool_slug=f"{app_name.upper()}_{action_name.upper()}",
                tool_schema=tool_schema,
                user_input=user_input,
                context=context
            )
            
            # Extract parameters from the structured response
            if llm_result and 'parameters' in llm_result:
                extracted_params = llm_result['parameters']
                logger.info(f"LLM extracted parameters: {list(extracted_params.keys())}")
                return extracted_params
            
            logger.warning("No parameters returned from LLM, using fallback")
            return await self._fallback_parameter_extraction(user_input, app_name, action_name)
            
        except Exception as e:
            logger.error(f"LLM parameter extraction failed: {str(e)}")
            return await self._fallback_parameter_extraction(user_input, app_name, action_name)

    async def _fallback_parameter_extraction(
        self,
        user_input: str,
        app_name: str,
        action_name: str
    ) -> Dict[str, Any]:
        """Enhanced fallback parameter extraction with dynamic schema discovery."""
        
        logger.info(f"Starting enhanced fallback parameter extraction for {app_name}.{action_name}")
        
        # Step 1: Try dynamic schema discovery first
        discovered_params = await self._discover_schema_and_generate(user_input, app_name, action_name)
        if discovered_params:
            logger.info(f"Successfully generated parameters using dynamic schema: {list(discovered_params.keys())}")
            return discovered_params
        
        # Step 2: Fall back to existing regex-based extraction
        logger.info("Dynamic schema discovery failed, using regex fallback")
        return await self._regex_based_extraction(user_input, app_name, action_name)
    
    async def _discover_schema_and_generate(
        self,
        user_input: str,
        app_name: str,
        action_name: str
    ) -> Optional[Dict[str, Any]]:
        """Discover API schema dynamically and generate parameters."""
        
        if not COMPOSIO_AVAILABLE:
            logger.warning("Composio not available for schema discovery")
            return None
        
        try:
            # Map app_name and action_name to Composio Action
            action_map = {
                ('gmail', 'send_email'): Action.GMAIL_SEND_EMAIL,
                ('gmail', 'fetch_emails'): Action.GMAIL_FETCH_EMAILS,
                ('gmail', 'create_draft'): Action.GMAIL_CREATE_EMAIL_DRAFT,
                ('gmail', 'reply'): Action.GMAIL_REPLY_TO_THREAD,
                # Add more mappings as needed for other apps
            }
            
            action_key = (app_name.lower(), action_name.lower())
            if action_key not in action_map:
                logger.info(f"No action mapping found for {action_key}")
                return None
            
            composio_action = action_map[action_key]
            logger.info(f"Using Composio action: {composio_action}")
            
            # Test with empty params to discover required fields
            toolset = ComposioToolSet()
            try:
                result = toolset.execute_action(
                    action=composio_action,
                    params={},
                    entity_id="default"
                )
                logger.warning("Unexpected success with empty params - no required fields discovered")
                return None
                
            except Exception as e:
                error_msg = str(e)
                logger.info(f"Got expected error for schema discovery: {error_msg}")
                
                # Extract required fields from error message
                required_fields = self._extract_required_fields_from_error(error_msg)
                if required_fields:
                    logger.info(f"Discovered required fields: {required_fields}")
                    
                    # Generate parameters based on discovered schema
                    return self._generate_parameters_with_schema(user_input, required_fields, app_name)
                else:
                    logger.warning("Could not parse required fields from error")
                    return None
                    
        except Exception as e:
            logger.error(f"Schema discovery failed: {str(e)}")
            return None
    
    def _extract_required_fields_from_error(self, error_msg: str) -> List[str]:
        """Extract required field names from Composio API error messages."""
        
        # Pattern: "Following fields are missing: {'field1', 'field2'}"
        missing_pattern = r"missing.*?[{]([^}]+)[}]"
        matches = re.findall(missing_pattern, error_msg, re.IGNORECASE)
        
        if matches:
            fields_str = matches[0]
            # Parse field names from the set notation
            field_names = []
            
            # Split by comma and clean each field
            for field in fields_str.split(','):
                clean_field = field.strip().strip("'\"")
                if clean_field:
                    field_names.append(clean_field)
            
            return field_names
        
        return []
    
    def _generate_parameters_with_schema(
        self,
        user_input: str,
        required_fields: List[str],
        app_name: str
    ) -> Dict[str, Any]:
        """Generate parameters based on discovered schema and user input."""
        
        generated_params = {}
        
        for field in required_fields:
            if 'email' in field.lower() or 'recipient' in field.lower():
                # Extract email addresses
                email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                email_matches = re.findall(email_pattern, user_input)
                if email_matches:
                    generated_params[field] = email_matches[0]
            
            elif 'subject' in field.lower() or 'title' in field.lower():
                # Extract subject from quotes or after keywords
                subject_patterns = [
                    r"subject[:\s]+['\"]([^'\"]+)['\"]",
                    r"about[:\s]+['\"]([^'\"]+)['\"]",  
                    r"regarding[:\s]+['\"]([^'\"]+)['\"]",
                    r"with[:\s]+subject[:\s]+['\"]([^'\"]+)['\"]",
                    r"titled?\s+['\"]([^'\"]+)['\"]"
                ]
                
                for pattern in subject_patterns:
                    matches = re.findall(pattern, user_input, re.IGNORECASE)
                    if matches:
                        generated_params[field] = matches[0]
                        break
            
            elif 'body' in field.lower() or 'message' in field.lower() or 'content' in field.lower():
                # Generate body based on user intent
                body_content = self._generate_email_body(user_input)
                generated_params[field] = body_content
        
        return generated_params
    
    def _generate_email_body(self, user_input: str) -> str:
        """Generate email body content based on user intent."""
        
        # Extract the main intent/action from the user input
        intent_patterns = [
            (r"tell(?:ing)?\s+them\s+(?:about\s+)?(.+?)(?:\s+(?:with|to|and)|$)", "I wanted to tell you about {}"),
            (r"ask(?:ing)?\s+them\s+to\s+(.+?)(?:\s+(?:with|and)|$)", "Could you please {}?"),
            (r"inform(?:ing)?\s+them\s+(?:about\s+)?(.+?)(?:\s+(?:with|and)|$)", "I'd like to inform you about {}"),
            (r"with\s+details\s+about\s+(.+?)(?:\s+(?:with|and)|$)", "Here are the details about {}")
        ]
        
        body_parts = ["Hello!"]
        
        # Try to extract specific intent
        for pattern, template in intent_patterns:
            matches = re.findall(pattern, user_input, re.IGNORECASE)
            if matches:
                content = matches[0].strip()
                body_parts.append(template.format(content))
                break
        else:
            # Default body if no specific intent found
            body_parts.append("This email was generated automatically based on your request.")
        
        body_parts.extend([
            "",
            "Best regards,", 
            "AI Assistant"
        ])
        
        return "\n".join(body_parts)
    
    async def _regex_based_extraction(
        self,
        user_input: str,
        app_name: str,
        action_name: str
    ) -> Dict[str, Any]:
        """Original regex-based parameter extraction as fallback."""
        
        params = {}
        input_lower = user_input.lower()
        
        # Common patterns for all apps
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, user_input)
        
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        urls = re.findall(url_pattern, user_input)
        
        # Date patterns (basic)
        date_patterns = [
            r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
            r'(\d{2}/\d{2}/\d{4})',  # MM/DD/YYYY
            r'(today|tomorrow|yesterday)',
        ]
        dates = []
        for pattern in date_patterns:
            dates.extend(re.findall(pattern, input_lower))
        
        # App-specific extraction
        if app_name == 'gmail':
            if emails:
                params['to'] = emails[0]
                # If multiple emails, add others as cc
                if len(emails) > 1:
                    params['cc'] = emails[1:]
            
            # Enhanced subject extraction
            subject_patterns = [
                r'about\s+["\']?([^"\']+?)["\']?(?:\s+to|\s*$)',
                r'subject[:\s]+["\']?([^"\']+?)["\']?(?:\s+to|\s*$)',
                r'titled?\s+["\']([^"\']+)["\']',
                r'called\s+["\']([^"\']+)["\']',
                r're:\s+([^"\']+?)(?:\s+to|\s*$)',
                r'regarding\s+([^"\']+?)(?:\s+to|\s*$)'
            ]
            
            for pattern in subject_patterns:
                match = re.search(pattern, input_lower, re.IGNORECASE)
                if match:
                    params['subject'] = match.group(1).strip()
                    break
            
            # Body extraction from common phrases
            body_patterns = [
                r'tell them\s+(.+)',
                r'message[:\s]+(.+)',
                r'body[:\s]+(.+)',
                r'content[:\s]+(.+)'
            ]
            
            for pattern in body_patterns:
                match = re.search(pattern, input_lower)
                if match:
                    params['body'] = match.group(1).strip()
                    break
            
            # If no specific body found but no subject, use input as body
            if 'body' not in params and 'subject' not in params:
                params['body'] = user_input
        
        elif app_name == 'twitter' or app_name == 'x':
            # For tweets, extract text content
            tweet_patterns = [
                r'post[:\s]+["\']?([^"\']+?)["\']?(?:\s*$)',
                r'tweet[:\s]+["\']?([^"\']+?)["\']?(?:\s*$)',
                r'say[:\s]+["\']?([^"\']+?)["\']?(?:\s*$)',
                r'["\']([^"\']{1,280})["\']',  # Quoted text under 280 chars
            ]
            
            for pattern in tweet_patterns:
                match = re.search(pattern, user_input, re.IGNORECASE)
                if match:
                    params['text'] = match.group(1).strip()
                    break
            
            # If no specific pattern, use whole input as text
            if 'text' not in params:
                params['text'] = user_input
            
            # Detect mentions and hashtags
            mentions = re.findall(r'@(\w+)', user_input)
            hashtags = re.findall(r'#(\w+)', user_input)
            
            if mentions:
                params['mentions'] = mentions
            if hashtags:
                params['hashtags'] = hashtags
        
        elif app_name == 'github':
            # Enhanced GitHub extraction
            if action_name in ['create_issue', 'create_repository']:
                title_patterns = [
                    r'create\s+(?:issue|repository)\s+(?:for|about|titled?)\s+["\']([^"\']+)["\']',
                    r'(?:issue|repo|repository)\s+["\']([^"\']+)["\']',
                    r'called\s+["\']([^"\']+)["\']',
                    r'titled?\s+["\']([^"\']+)["\']',
                    r'named?\s+["\']([^"\']+)["\']'
                ]
                
                for pattern in title_patterns:
                    match = re.search(pattern, input_lower)
                    if match:
                        if action_name == 'create_issue':
                            params['title'] = match.group(1)
                        elif action_name == 'create_repository':
                            params['name'] = match.group(1)
                        break
                
                # Extract description/body
                desc_patterns = [
                    r'description[:\s]+(.+)',
                    r'about[:\s]+(.+)',
                    r'details[:\s]+(.+)',
                    r'body[:\s]+(.+)'
                ]
                
                for pattern in desc_patterns:
                    match = re.search(pattern, input_lower)
                    if match:
                        if action_name == 'create_issue':
                            params['body'] = match.group(1).strip()
                        elif action_name == 'create_repository':
                            params['description'] = match.group(1).strip()
                        break
        
        elif app_name == 'slack':
            # Slack message extraction
            channel_patterns = [
                r'(?:to|in)\s+(#\w+)',
                r'channel\s+(#?\w+)',
                r'(?:to|in)\s+(@\w+)'
            ]
            
            for pattern in channel_patterns:
                match = re.search(pattern, input_lower)
                if match:
                    channel = match.group(1)
                    if not channel.startswith('#') and not channel.startswith('@'):
                        channel = f'#{channel}'
                    params['channel'] = channel
                    break
            
            # Extract message text
            message_patterns = [
                r'send\s+["\']?([^"\']+?)["\']?(?:\s+to|\s*$)',
                r'message[:\s]+["\']?([^"\']+?)["\']?(?:\s+to|\s*$)',
                r'say\s+["\']?([^"\']+?)["\']?(?:\s+to|\s*$)'
            ]
            
            for pattern in message_patterns:
                match = re.search(pattern, user_input, re.IGNORECASE)
                if match:
                    params['text'] = match.group(1).strip()
                    break
            
            if 'text' not in params:
                params['text'] = user_input
        
        elif app_name == 'google_calendar':
            # Calendar event extraction
            event_patterns = [
                r'create\s+(?:event|meeting)\s+["\']?([^"\']+?)["\']?(?:\s+on|\s*$)',
                r'schedule\s+["\']?([^"\']+?)["\']?(?:\s+on|\s*$)',
                r'event\s+["\']?([^"\']+?)["\']?(?:\s+on|\s*$)'
            ]
            
            for pattern in event_patterns:
                match = re.search(pattern, input_lower)
                if match:
                    params['summary'] = match.group(1).strip()
                    break
            
            # Extract dates/times if present
            if dates:
                params['start_time'] = dates[0]
                if len(dates) > 1:
                    params['end_time'] = dates[1]
            
            # Extract attendees (emails)
            if emails:
                params['attendees'] = emails
        
        # Common parameter extraction for URLs
        if urls and 'url' not in params:
            params['url'] = urls[0]
        
        # Extract quoted strings as potential titles/names
        quoted_strings = re.findall(r'["\']([^"\']+)["\']', user_input)
        if quoted_strings and 'title' not in params and 'name' not in params and 'text' not in params:
            if app_name == 'github' and action_name == 'create_repository':
                params['name'] = quoted_strings[0]
            elif app_name == 'github' and action_name == 'create_issue':
                params['title'] = quoted_strings[0]
            elif 'subject' not in params and app_name == 'gmail':
                params['subject'] = quoted_strings[0]
        
        logger.info(f"Enhanced fallback extraction found {len(params)} parameters for {app_name}.{action_name}")
        return params

    async def _enhance_with_patterns(
        self,
        base_params: Dict[str, Any],
        app_name: str,
        action_name: str,
        tool_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enhance parameters using app-specific patterns."""
        
        enhanced = base_params.copy()
        app_patterns = self.APP_PARAMETER_PATTERNS.get(app_name, {})
        action_patterns = app_patterns.get(action_name, {})
        
        # Apply default values
        for param_name, pattern_info in action_patterns.items():
            if param_name not in enhanced and 'default' in pattern_info:
                enhanced[param_name] = pattern_info['default']
                logger.debug(f"Applied default value for {param_name}: {pattern_info['default']}")
        
        # Validate enum values
        for param_name, param_value in enhanced.items():
            pattern_info = action_patterns.get(param_name, {})
            if 'enum_values' in pattern_info:
                if param_value not in pattern_info['enum_values']:
                    # Try to find a close match
                    close_match = self._find_closest_enum_value(param_value, pattern_info['enum_values'])
                    if close_match:
                        enhanced[param_name] = close_match
                        logger.info(f"Corrected enum value for {param_name}: {param_value} → {close_match}")
        
        # Apply type conversions
        schema_params = tool_schema.get('parameters', {})
        for param_name, param_value in enhanced.items():
            if param_name in schema_params:
                param_schema = schema_params[param_name]
                expected_type = param_schema.get('type')
                
                try:
                    converted_value = self._convert_parameter_type(param_value, expected_type)
                    if converted_value != param_value:
                        enhanced[param_name] = converted_value
                        logger.debug(f"Type conversion for {param_name}: {type(param_value)} → {type(converted_value)}")
                except Exception as e:
                    logger.warning(f"Failed to convert parameter {param_name}: {str(e)}")
        
        return enhanced

    async def _validate_parameters(
        self,
        parameters: Dict[str, Any],
        tool_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate parameters against tool schema."""
        
        validated = {}
        schema_params = tool_schema.get('parameters', {})
        required_params = set(tool_schema.get('required_parameters', []))
        
        # Validate each parameter
        for param_name, param_value in parameters.items():
            if param_name in schema_params:
                param_schema = schema_params[param_name]
                
                try:
                    # Type validation and conversion
                    validated_value = self._validate_parameter_value(param_value, param_schema)
                    validated[param_name] = validated_value
                except ValueError as e:
                    logger.warning(f"Parameter {param_name} validation failed: {str(e)}")
                    # Skip invalid parameters rather than failing completely
                    continue
            else:
                # Unknown parameter - include with warning
                logger.warning(f"Unknown parameter {param_name} for this tool")
                validated[param_name] = param_value
        
        # Check for missing required parameters
        missing_required = required_params - set(validated.keys())
        if missing_required:
            logger.warning(f"Missing required parameters: {list(missing_required)}")
            # Don't fail here - let the execution handle missing required params
        
        return validated

    async def _get_tool_schema(self, tool_slug: str) -> Dict[str, Any]:
        """Get tool schema with caching."""
        
        if tool_slug in self._schema_cache:
            return self._schema_cache[tool_slug]
        
        try:
            # Get the actual schema from Composio service
            schema = await self.composio_service.get_tool_schema(tool_slug)
            
            # Normalize the schema structure for consistency
            normalized_schema = {
                'parameters': schema.get('parameters', {}),
                'required_parameters': schema.get('required_parameters', []),
                'name': schema.get('name', tool_slug),
                'description': schema.get('description', f'Tool: {tool_slug}'),
                'app': schema.get('app', 'unknown'),
                'raw_schema': schema
            }
            
            self._schema_cache[tool_slug] = normalized_schema
            logger.info(f"Cached schema for {tool_slug} with {len(normalized_schema['parameters'])} parameters")
            return normalized_schema
            
        except Exception as e:
            logger.error(f"Failed to get schema for {tool_slug}: {str(e)}")
            
            # Return a fallback schema structure
            fallback_schema = {
                'parameters': {},
                'required_parameters': [],
                'name': tool_slug,
                'description': f'Tool: {tool_slug}',
                'app': 'unknown',
                'error': str(e)
            }
            
            # Cache the fallback to avoid repeated failures
            self._schema_cache[tool_slug] = fallback_schema
            return fallback_schema

    def _convert_parameter_type(self, value: Any, expected_type: str) -> Any:
        """Convert parameter to expected type."""
        
        if expected_type == 'string':
            return str(value) if value is not None else ""
        elif expected_type == 'integer':
            return int(float(value)) if value not in [None, "", []] else 0
        elif expected_type == 'number':
            return float(value) if value not in [None, "", []] else 0.0
        elif expected_type == 'boolean':
            if isinstance(value, bool):
                return value
            elif isinstance(value, str):
                return value.lower() in ['true', 'yes', '1', 'on', 'enable']
            else:
                return bool(value)
        elif expected_type == 'array':
            if isinstance(value, list):
                return value
            elif isinstance(value, str):
                # Try to parse as comma-separated values
                return [item.strip() for item in value.split(',') if item.strip()]
            else:
                return [value] if value is not None else []
        elif expected_type == 'object':
            if isinstance(value, dict):
                return value
            elif isinstance(value, str):
                try:
                    return json.loads(value)
                except:
                    return {'value': value}
            else:
                return {'value': value}
        
        return value

    def _validate_parameter_value(self, value: Any, param_schema: Dict[str, Any]) -> Any:
        """Validate a single parameter value against its schema."""
        
        param_type = param_schema.get('type', 'string')
        
        # Convert type first
        converted_value = self._convert_parameter_type(value, param_type)
        
        # Validate constraints
        if param_type in ['integer', 'number']:
            minimum = param_schema.get('minimum')
            maximum = param_schema.get('maximum')
            
            if minimum is not None and converted_value < minimum:
                raise ValueError(f"Value {converted_value} is below minimum {minimum}")
            if maximum is not None and converted_value > maximum:
                raise ValueError(f"Value {converted_value} is above maximum {maximum}")
        
        elif param_type == 'string':
            min_length = param_schema.get('minLength')
            max_length = param_schema.get('maxLength')
            pattern = param_schema.get('pattern')
            
            if min_length is not None and len(converted_value) < min_length:
                raise ValueError(f"String too short: {len(converted_value)} < {min_length}")
            if max_length is not None and len(converted_value) > max_length:
                raise ValueError(f"String too long: {len(converted_value)} > {max_length}")
            if pattern and not re.match(pattern, converted_value):
                raise ValueError(f"String doesn't match pattern: {pattern}")
        
        elif param_type == 'array':
            min_items = param_schema.get('minItems')
            max_items = param_schema.get('maxItems')
            
            if min_items is not None and len(converted_value) < min_items:
                raise ValueError(f"Array too short: {len(converted_value)} < {min_items}")
            if max_items is not None and len(converted_value) > max_items:
                raise ValueError(f"Array too long: {len(converted_value)} > {max_items}")
        
        # Validate enum values
        enum_values = param_schema.get('enum')
        if enum_values and converted_value not in enum_values:
            raise ValueError(f"Value {converted_value} not in allowed values: {enum_values}")
        
        return converted_value

    def _find_closest_enum_value(self, value: str, enum_values: List[str]) -> Optional[str]:
        """Find the closest matching enum value."""
        
        value_lower = str(value).lower()
        
        # Exact match (case insensitive)
        for enum_val in enum_values:
            if enum_val.lower() == value_lower:
                return enum_val
        
        # Partial match
        for enum_val in enum_values:
            if value_lower in enum_val.lower() or enum_val.lower() in value_lower:
                return enum_val
        
        return None

    async def _generate_parameter_suggestions(
        self,
        param_name: str,
        param_info: Dict[str, Any],
        partial_input: str,
        context: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Generate intelligent suggestions for a parameter."""
        
        suggestions = []
        param_type = param_info.get('type', 'string')
        
        # Type-specific suggestions
        if param_type == 'email':
            suggestions.extend(['user@example.com', 'contact@company.com'])
        elif param_type == 'boolean':
            suggestions.extend(['true', 'false'])
        elif param_type == 'date':
            now = datetime.now()
            suggestions.extend([
                now.isoformat(),
                (now + timedelta(days=1)).isoformat(),
                (now + timedelta(hours=2)).isoformat()
            ])
        elif 'enum' in param_info:
            suggestions.extend(param_info['enum'][:5])  # Top 5 enum values
        
        # Context-based suggestions
        if context:
            if param_name == 'to' and 'user_email' in context:
                suggestions.insert(0, context['user_email'])
            elif param_name == 'subject' and 'last_subject' in context:
                suggestions.insert(0, f"Re: {context['last_subject']}")
        
        # Input-based suggestions
        if partial_input:
            input_words = partial_input.lower().split()
            if param_name == 'subject' or param_name == 'title':
                # Extract potential subjects from input
                for i, word in enumerate(input_words):
                    if word in ['about', 'regarding', 'subject', 'title']:
                        if i + 1 < len(input_words):
                            suggestion = ' '.join(input_words[i+1:i+4])  # Next 3 words
                            suggestions.insert(0, suggestion)
        
        return suggestions[:3]  # Limit to 3 suggestions

    async def _generate_default_parameter_value(
        self,
        param_name: str,
        param_info: Dict[str, Any],
        app_name: str,
        action_name: str
    ) -> Any:
        """Generate a sensible default value for a parameter."""
        
        param_type = param_info.get('type', 'string')
        
        # Check for explicit default
        if 'default' in param_info:
            return param_info['default']
        
        # App-specific defaults
        app_patterns = self.APP_PARAMETER_PATTERNS.get(app_name, {})
        action_patterns = app_patterns.get(action_name, {})
        if param_name in action_patterns and 'default' in action_patterns[param_name]:
            return action_patterns[param_name]['default']
        
        # Type-based defaults
        if param_type == 'boolean':
            return False
        elif param_type == 'integer':
            return 1
        elif param_type == 'number':
            return 1.0
        elif param_type == 'array':
            return []
        elif param_type == 'object':
            return {}
        elif param_type == 'string':
            # Parameter name-based defaults
            if param_name == 'subject':
                return "No Subject"
            elif param_name == 'body' or param_name == 'text':
                return "Auto-generated content"
            elif param_name == 'title':
                return "Untitled"
            else:
                return ""
        
        return None

    async def _store_generation_history(
        self,
        user_input: str,
        app_name: str,
        action_name: str,
        generated_params: Dict[str, Any]
    ):
        """Store generation history for learning and analytics."""
        
        history_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'user_input': user_input,
            'app_name': app_name,
            'action_name': action_name,
            'generated_params': generated_params,
            'success': len(generated_params) > 0
        }
        
        self._generation_history.append(history_entry)
        
        # Keep only last 1000 entries
        if len(self._generation_history) > 1000:
            self._generation_history = self._generation_history[-1000:]

    async def get_generation_analytics(self) -> Dict[str, Any]:
        """Get analytics on parameter generation performance."""
        
        if not self._generation_history:
            return {'error': 'No generation history available'}
        
        total_generations = len(self._generation_history)
        successful_generations = sum(1 for entry in self._generation_history if entry['success'])
        
        # App-wise statistics
        app_stats = {}
        for entry in self._generation_history:
            app = entry['app_name']
            if app not in app_stats:
                app_stats[app] = {'total': 0, 'successful': 0}
            app_stats[app]['total'] += 1
            if entry['success']:
                app_stats[app]['successful'] += 1
        
        # Calculate success rates
        for app in app_stats:
            app_stats[app]['success_rate'] = app_stats[app]['successful'] / app_stats[app]['total']
        
        return {
            'total_generations': total_generations,
            'successful_generations': successful_generations,
            'overall_success_rate': successful_generations / total_generations,
            'app_statistics': app_stats,
            'cache_stats': {
                'schemas_cached': len(self._schema_cache),
                'patterns_cached': len(self._pattern_cache)
            },
            'generated_at': datetime.utcnow().isoformat()
        }