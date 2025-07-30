import os
import json
import asyncio
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
import logging
from .composio_service import ComposioService

logger = logging.getLogger(__name__)


class ComposioToolDiscovery:
    """
    Handles dynamic tool discovery, caching, and scenario-to-tool mapping for Composio integrations.
    Provides intelligent tool selection and parameter resolution.
    """
    
    # Predefined scenario-to-tool mappings based on SRS requirements
    SCENARIO_TOOL_MAPPINGS = {
        'email': {
            'primary_tools': [
                'GMAIL_FETCH_EMAILS',
                'GMAIL_SEND_EMAIL', 
                'GMAIL_CREATE_EMAIL_DRAFT'
            ],
            'optional_tools': [
                'TWITTER_CREATION_OF_A_POST'  # For email-to-X workflow
            ],
            'required_apps': ['gmail'],
            'optional_apps': ['twitter']
        },
        'flight_booking': {
            'primary_tools': [
                'SKYSCANNER_SEARCH_FLIGHTS',
                'SKYSCANNER_BOOK_FLIGHT',
                'STRIPE_PAYMENT'
            ],
            'optional_tools': [
                'GMAIL_SEND_EMAIL'  # For confirmation emails
            ],
            'required_apps': ['skyscanner', 'stripe'],
            'optional_apps': ['gmail']
        },
        'meeting_scheduling': {
            'primary_tools': [
                'GOOGLE_CALENDAR_FIND_FREE_TIME',
                'GOOGLE_CALENDAR_CREATE_EVENT',
                'ZOOM_CREATE_MEETING'
            ],
            'optional_tools': [
                'GMAIL_SEND_EMAIL'  # For meeting invitations
            ],
            'required_apps': ['google_calendar', 'zoom'],
            'optional_apps': ['gmail']
        },
        'trip_planning': {
            'primary_tools': [
                'SKYSCANNER_SEARCH_FLIGHTS',
                'BOOKING_SEARCH_HOTELS',
                'TRIPADVISOR_SEARCH_ATTRACTIONS'
            ],
            'optional_tools': [
                'GMAIL_SEND_EMAIL',  # For itinerary sharing
                'STRIPE_PAYMENT'  # For bookings
            ],
            'required_apps': ['skyscanner', 'booking', 'tripadvisor'],
            'optional_apps': ['gmail', 'stripe']
        },
        'food_ordering': {
            'primary_tools': [
                'DOORDASH_SEARCH_RESTAURANTS',
                'DOORDASH_PLACE_ORDER',
                'STRIPE_PAYMENT'
            ],
            'optional_tools': [
                'TWITTER_CREATION_OF_A_POST'  # For sharing food experiences
            ],
            'required_apps': ['doordash', 'stripe'],
            'optional_apps': ['twitter']
        },
        'x_posting': {
            'primary_tools': [
                'TWITTER_CREATION_OF_A_POST',
                'TWITTER_UPLOAD_MEDIA'
            ],
            'optional_tools': [],
            'required_apps': ['twitter'],
            'optional_apps': []
        }
    }
    
    def __init__(self, composio_service: ComposioService):
        self.composio_service = composio_service
        
        # Discovery cache
        self._scenario_tools_cache: Dict[str, Dict[str, Any]] = {}
        self._tool_schemas_cache: Dict[str, Dict[str, Any]] = {}
        self._apps_tools_cache: Dict[str, List[str]] = {}
        
        # Cache TTL
        self._cache_ttl = int(os.getenv('COMPOSIO_TOOL_CACHE_TTL', '3600'))  # 1 hour
        self._last_discovery_time: Dict[str, datetime] = {}
        
        logger.info("ComposioToolDiscovery initialized")

    async def discover_scenario_tools(self, scenario: str, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Discover and validate tools available for a specific scenario.
        
        Args:
            scenario: Scenario name (email, flight_booking, etc.)
            force_refresh: Force refresh of cached data
            
        Returns:
            Dictionary containing available tools, missing tools, and metadata
        """
        try:
            cache_key = f"scenario_{scenario}"
            
            # Check cache validity
            if not force_refresh and self._is_cache_valid(cache_key):
                logger.debug(f"Returning cached tools for scenario {scenario}")
                return self._scenario_tools_cache[cache_key]
            
            if scenario not in self.SCENARIO_TOOL_MAPPINGS:
                raise ValueError(f"Unknown scenario: {scenario}")
            
            scenario_config = self.SCENARIO_TOOL_MAPPINGS[scenario]
            
            # Discover tools for required and optional apps
            all_apps = scenario_config['required_apps'] + scenario_config['optional_apps']
            app_tools = {}
            
            for app in all_apps:
                try:
                    tools = await self.composio_service.discover_tools(app)
                    app_tools[app] = tools
                    logger.debug(f"Discovered {len(tools)} tools for app {app}")
                except Exception as e:
                    logger.error(f"Failed to discover tools for app {app}: {str(e)}")
                    app_tools[app] = []
            
            # Map available tools to scenario requirements
            available_tools = []
            missing_tools = []
            
            for tool_slug in scenario_config['primary_tools'] + scenario_config['optional_tools']:
                tool_found = False
                
                for app, tools in app_tools.items():
                    for tool in tools:
                        if tool['slug'] == tool_slug or tool['name'] == tool_slug:
                            available_tools.append({
                                'slug': tool_slug,
                                'name': tool['name'],
                                'app': app,
                                'description': tool['description'],
                                'is_primary': tool_slug in scenario_config['primary_tools'],
                                'schema': await self._get_cached_tool_schema(tool_slug)
                            })
                            tool_found = True
                            break
                    
                    if tool_found:
                        break
                
                if not tool_found:
                    missing_tools.append({
                        'slug': tool_slug,
                        'is_primary': tool_slug in scenario_config['primary_tools']
                    })
            
            # Calculate scenario completeness
            primary_tools_available = len([t for t in available_tools if t['is_primary']])
            primary_tools_required = len(scenario_config['primary_tools'])
            completeness_percentage = (primary_tools_available / primary_tools_required) * 100 if primary_tools_required > 0 else 0
            
            result = {
                'scenario': scenario,
                'available_tools': available_tools,
                'missing_tools': missing_tools,
                'apps_discovered': list(app_tools.keys()),
                'completeness': {
                    'percentage': completeness_percentage,
                    'primary_tools_available': primary_tools_available,
                    'primary_tools_required': primary_tools_required,
                    'is_functional': completeness_percentage >= 100
                },
                'metadata': {
                    'discovered_at': datetime.utcnow().isoformat(),
                    'scenario_config': scenario_config
                }
            }
            
            # Cache the result
            self._scenario_tools_cache[cache_key] = result
            self._last_discovery_time[cache_key] = datetime.utcnow()
            
            logger.info(f"Discovered tools for scenario {scenario}: {completeness_percentage:.1f}% complete")
            return result
            
        except Exception as e:
            logger.error(f"Error discovering tools for scenario {scenario}: {str(e)}")
            raise
    
    async def discover_app_tools(self, app_name: str) -> List[Dict[str, Any]]:
        """
        Discover all available tools for a specific app.
        
        Args:
            app_name: Name of the app (e.g., 'gmail', 'twitter', 'github')
            
        Returns:
            List of available tools for the app
        """
        try:
            logger.info(f"Discovering tools for app: {app_name}")
            
            # Use the composio service to discover tools for the app
            tools = await self.composio_service.discover_tools(app_name)
            
            logger.info(f"Found {len(tools)} tools for app {app_name}")
            return tools
            
        except Exception as e:
            logger.error(f"Error discovering tools for app {app_name}: {str(e)}")
            raise

    async def get_tools_for_task_tree(self, task_tree: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get and validate tools needed for executing a task tree.
        
        Args:
            task_tree: Task tree structure
            
        Returns:
            Tools mapping and validation result
        """
        try:
            required_tools = set()
            
            # Extract tool requirements from task tree
            def extract_tools(node):
                if isinstance(node, dict):
                    if 'tool' in node:
                        required_tools.add(node['tool'])
                    if 'function' in node:
                        # Map function names to tool slugs if needed
                        tool_slug = self._map_function_to_tool(node['function'])
                        if tool_slug:
                            required_tools.add(tool_slug)
                    
                    # Recursively process child nodes
                    for key, value in node.items():
                        if isinstance(value, (dict, list)):
                            extract_tools(value)
                elif isinstance(node, list):
                    for item in node:
                        extract_tools(item)
            
            extract_tools(task_tree)
            
            # Get tool schemas and validate availability
            tools_info = {}
            missing_tools = []
            
            for tool_slug in required_tools:
                try:
                    schema = await self._get_cached_tool_schema(tool_slug)
                    tools_info[tool_slug] = schema
                except Exception as e:
                    logger.error(f"Failed to get schema for tool {tool_slug}: {str(e)}")
                    missing_tools.append(tool_slug)
            
            result = {
                'required_tools': list(required_tools),
                'tools_info': tools_info,
                'missing_tools': missing_tools,
                'is_executable': len(missing_tools) == 0,
                'metadata': {
                    'analyzed_at': datetime.utcnow().isoformat(),
                    'total_tools': len(required_tools)
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting tools for task tree: {str(e)}")
            raise

    async def find_alternative_tools(self, missing_tool: str, scenario: str) -> List[Dict[str, Any]]:
        """
        Find alternative tools that could replace a missing tool.
        
        Args:
            missing_tool: The tool that's missing
            scenario: Current scenario context
            
        Returns:
            List of alternative tools with similarity scores
        """
        try:
            # Get all available tools
            all_tools = await self.composio_service.discover_tools()
            
            # Simple alternative matching based on:
            # 1. Similar app (if missing tool has app prefix)
            # 2. Similar functionality keywords
            # 3. Scenario context
            
            alternatives = []
            
            missing_tool_lower = missing_tool.lower()
            missing_app = missing_tool_lower.split('_')[0] if '_' in missing_tool_lower else None
            
            for tool in all_tools:
                tool_name_lower = tool['name'].lower()
                tool_slug_lower = tool['slug'].lower()
                
                similarity_score = 0
                reasons = []
                
                # App match
                if missing_app and tool['app'] and missing_app in tool['app'].lower():
                    similarity_score += 50
                    reasons.append(f"Same app ({tool['app']})")
                
                # Functionality keywords match
                keywords = ['search', 'create', 'send', 'fetch', 'book', 'upload', 'post']
                for keyword in keywords:
                    if keyword in missing_tool_lower and keyword in tool_name_lower:
                        similarity_score += 20
                        reasons.append(f"Similar function ({keyword})")
                
                # Description similarity (basic keyword matching)
                if tool.get('description'):
                    desc_lower = tool['description'].lower()
                    for keyword in missing_tool_lower.split('_'):
                        if keyword in desc_lower and len(keyword) > 2:
                            similarity_score += 10
                            reasons.append(f"Description match ({keyword})")
                
                if similarity_score > 0:
                    alternatives.append({
                        'tool': tool,
                        'similarity_score': similarity_score,
                        'reasons': reasons
                    })
            
            # Sort by similarity score
            alternatives.sort(key=lambda x: x['similarity_score'], reverse=True)
            
            # Return top 5 alternatives
            return alternatives[:5]
            
        except Exception as e:
            logger.error(f"Error finding alternatives for {missing_tool}: {str(e)}")
            return []

    async def validate_tool_chain(self, tool_chain: List[str]) -> Dict[str, Any]:
        """
        Validate that a chain of tools can be executed in sequence.
        
        Args:
            tool_chain: List of tool slugs in execution order
            
        Returns:
            Validation result with dependency analysis
        """
        try:
            validation_result = {
                'valid': True,
                'issues': [],
                'dependencies': {},
                'execution_plan': []
            }
            
            tool_schemas = {}
            
            # Get schemas for all tools
            for tool_slug in tool_chain:
                try:
                    schema = await self._get_cached_tool_schema(tool_slug)
                    tool_schemas[tool_slug] = schema
                except Exception as e:
                    validation_result['valid'] = False
                    validation_result['issues'].append(f"Cannot get schema for {tool_slug}: {str(e)}")
            
            # Analyze dependencies and data flow
            for i, tool_slug in enumerate(tool_chain):
                if tool_slug not in tool_schemas:
                    continue
                
                schema = tool_schemas[tool_slug]
                execution_step = {
                    'step': i + 1,
                    'tool': tool_slug,
                    'dependencies': [],
                    'outputs': [],
                    'required_inputs': schema.get('required_parameters', [])
                }
                
                # Check if required inputs can be satisfied by previous tools
                for param in schema.get('required_parameters', []):
                    param_satisfied = False
                    
                    # Check if any previous tool can provide this parameter
                    for j in range(i):
                        prev_tool = tool_chain[j]
                        if prev_tool in tool_schemas:
                            # This is a simplified check - in reality, you'd need to analyze
                            # output schemas to determine if they can provide required inputs
                            execution_step['dependencies'].append(prev_tool)
                            param_satisfied = True
                            break
                    
                    if not param_satisfied and i > 0:  # First tool doesn't need dependencies
                        validation_result['issues'].append(
                            f"Tool {tool_slug} requires parameter '{param}' but no previous tool provides it"
                        )
                
                validation_result['execution_plan'].append(execution_step)
            
            # Mark as invalid if issues found
            if validation_result['issues']:
                validation_result['valid'] = False
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error validating tool chain: {str(e)}")
            return {
                'valid': False,
                'issues': [f"Validation error: {str(e)}"],
                'dependencies': {},
                'execution_plan': []
            }

    async def get_scenario_completeness_report(self) -> Dict[str, Any]:
        """
        Generate a completeness report for all scenarios.
        
        Returns:
            Comprehensive report of scenario tool availability
        """
        try:
            report = {
                'scenarios': {},
                'overall_stats': {
                    'total_scenarios': len(self.SCENARIO_TOOL_MAPPINGS),
                    'functional_scenarios': 0,
                    'total_tools_required': 0,
                    'total_tools_available': 0
                },
                'generated_at': datetime.utcnow().isoformat()
            }
            
            for scenario in self.SCENARIO_TOOL_MAPPINGS.keys():
                scenario_tools = await self.discover_scenario_tools(scenario)
                report['scenarios'][scenario] = scenario_tools
                
                if scenario_tools['completeness']['is_functional']:
                    report['overall_stats']['functional_scenarios'] += 1
                
                report['overall_stats']['total_tools_required'] += scenario_tools['completeness']['primary_tools_required']
                report['overall_stats']['total_tools_available'] += scenario_tools['completeness']['primary_tools_available']
            
            # Calculate overall completeness
            if report['overall_stats']['total_tools_required'] > 0:
                overall_completeness = (
                    report['overall_stats']['total_tools_available'] / 
                    report['overall_stats']['total_tools_required']
                ) * 100
            else:
                overall_completeness = 0
            
            report['overall_stats']['completeness_percentage'] = overall_completeness
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating completeness report: {str(e)}")
            raise

    def _map_function_to_tool(self, function_name: str) -> Optional[str]:
        """
        Map legacy function names to Composio tool slugs.
        
        Args:
            function_name: Legacy function name
            
        Returns:
            Corresponding tool slug or None
        """
        # Legacy function to tool mapping
        function_tool_mapping = {
            'send_email': 'GMAIL_SEND_EMAIL',
            'fetch_emails': 'GMAIL_FETCH_EMAILS',
            'search_flights': 'SKYSCANNER_SEARCH_FLIGHTS',
            'book_flight': 'SKYSCANNER_BOOK_FLIGHT',
            'create_meeting': 'ZOOM_CREATE_MEETING',
            'schedule_event': 'GOOGLE_CALENDAR_CREATE_EVENT',
            'post_tweet': 'TWITTER_CREATION_OF_A_POST',
            'search_restaurants': 'DOORDASH_SEARCH_RESTAURANTS',
            'place_order': 'DOORDASH_PLACE_ORDER',
            'process_payment': 'STRIPE_PAYMENT'
        }
        
        return function_tool_mapping.get(function_name.lower())

    async def _get_cached_tool_schema(self, tool_slug: str) -> Dict[str, Any]:
        """
        Get tool schema from cache or fetch if not cached.
        
        Args:
            tool_slug: Tool slug
            
        Returns:
            Tool schema
        """
        if tool_slug in self._tool_schemas_cache:
            return self._tool_schemas_cache[tool_slug]
        
        schema = await self.composio_service.get_tool_schema(tool_slug)
        self._tool_schemas_cache[tool_slug] = schema
        
        return schema

    def _is_cache_valid(self, cache_key: str) -> bool:
        """
        Check if cached data is still valid.
        
        Args:
            cache_key: Cache key to check
            
        Returns:
            True if cache is valid
        """
        if cache_key not in self._last_discovery_time or cache_key not in self._scenario_tools_cache:
            return False
        
        last_update = self._last_discovery_time[cache_key]
        expiry_time = last_update + timedelta(seconds=self._cache_ttl)
        
        return datetime.utcnow() < expiry_time

    async def clear_cache(self):
        """Clear all discovery caches."""
        self._scenario_tools_cache.clear()
        self._tool_schemas_cache.clear()
        self._apps_tools_cache.clear()
        self._last_discovery_time.clear()
        
        logger.info("Tool discovery caches cleared")

    async def refresh_all_scenarios(self) -> Dict[str, Any]:
        """
        Refresh tool discovery for all scenarios.
        
        Returns:
            Refresh results summary
        """
        try:
            results = {}
            
            for scenario in self.SCENARIO_TOOL_MAPPINGS.keys():
                try:
                    scenario_tools = await self.discover_scenario_tools(scenario, force_refresh=True)
                    results[scenario] = {
                        'success': True,
                        'completeness': scenario_tools['completeness']['percentage'],
                        'tools_count': len(scenario_tools['available_tools'])
                    }
                except Exception as e:
                    results[scenario] = {
                        'success': False,
                        'error': str(e)
                    }
            
            summary = {
                'refreshed_scenarios': len(results),
                'successful_refreshes': len([r for r in results.values() if r['success']]),
                'results': results,
                'refreshed_at': datetime.utcnow().isoformat()
            }
            
            logger.info(f"Refreshed {summary['successful_refreshes']}/{summary['refreshed_scenarios']} scenarios")
            return summary
            
        except Exception as e:
            logger.error(f"Error refreshing all scenarios: {str(e)}")
            raise