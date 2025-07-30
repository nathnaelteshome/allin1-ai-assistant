import os
import json
import asyncio
from typing import Dict, Any, Optional
import logging
import firebase_admin
from firebase_admin import credentials, firestore

logger = logging.getLogger(__name__)


class FirebaseService:
    """
    Simple Firebase service wrapper for Firestore operations.
    """
    
    def __init__(self):
        self.app = None
        self.db = None
        self._initialize_firebase()
        
    def _initialize_firebase(self):
        """Initialize Firebase app and Firestore client."""
        try:
            # Check if we should use mock for testing
            if os.getenv('USE_MOCK_FIREBASE', 'false').lower() == 'true':
                self.db = MockFirestoreClient()
                logger.info("Using mock Firestore client for testing")
                return
            
            # Check if Firebase is already initialized
            if firebase_admin._apps:
                self.app = firebase_admin.get_app()
                logger.info("Using existing Firebase app")
            else:
                # Initialize Firebase
                service_account_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY_PATH')
                project_id = os.getenv('FIREBASE_PROJECT_ID')
                
                if service_account_path and os.path.exists(service_account_path):
                    cred = credentials.Certificate(service_account_path)
                    self.app = firebase_admin.initialize_app(cred, {
                        'projectId': project_id
                    })
                    logger.info(f"Firebase initialized with service account for project: {project_id}")
                else:
                    # Use default credentials (for deployment environments)
                    self.app = firebase_admin.initialize_app()
                    logger.info("Firebase initialized with default credentials")
            
            # Initialize Firestore
            self.db = firestore.client()
            logger.info("Firestore client initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {str(e)}")
            # For development, create a mock client
            self.db = MockFirestoreClient()
            logger.warning("Using mock Firestore client for development")
    
    def get_firestore_client(self):
        """Get the Firestore client instance."""
        return self.db


class MockFirestoreClient:
    """Mock Firestore client for development when Firebase is not configured."""
    
    def __init__(self):
        self._data = {}
        
    def collection(self, collection_name: str):
        return MockCollection(collection_name, self._data)


class MockCollection:
    """Mock Firestore collection."""
    
    def __init__(self, name: str, data: dict):
        self.name = name
        self._data = data
        
    def document(self, doc_id: str = None):
        if doc_id is None:
            doc_id = f"doc_{len(self._data)}"
        return MockDocument(self.name, doc_id, self._data)
        
    def where(self, field: str, op: str, value: Any):
        return MockQuery(self.name, self._data, [(field, op, value)])
        
    def order_by(self, field: str, direction=None):
        return MockQuery(self.name, self._data, [])
        
    async def get(self):
        collection_data = self._data.get(self.name, {})
        return [MockDocumentSnapshot(doc_id, data, self.name) 
                for doc_id, data in collection_data.items()]


class MockDocument:
    """Mock Firestore document."""
    
    def __init__(self, collection: str, doc_id: str, data: dict):
        self.collection = collection
        self.id = doc_id
        self._data = data
        
    async def set(self, data: dict):
        if self.collection not in self._data:
            self._data[self.collection] = {}
        self._data[self.collection][self.id] = data
        return self  # Return self to act like WriteResult
        
    async def get(self):
        collection_data = self._data.get(self.collection, {})
        doc_data = collection_data.get(self.id)
        return MockDocumentSnapshot(self.id, doc_data, self.collection)
        
    async def update(self, data: dict):
        if self.collection in self._data and self.id in self._data[self.collection]:
            self._data[self.collection][self.id].update(data)


class MockDocumentSnapshot:
    """Mock Firestore document snapshot."""
    
    def __init__(self, doc_id: str, data: dict, collection: str):
        self.id = doc_id
        self._data = data
        self.collection = collection
        
    @property
    def exists(self):
        return self._data is not None
        
    def to_dict(self):
        return self._data if self._data else {}


class MockQuery:
    """Mock Firestore query."""
    
    def __init__(self, collection: str, data: dict, filters: list):
        self.collection = collection
        self._data = data
        self._filters = filters
        
    def where(self, field: str, op: str, value: Any):
        return MockQuery(self.collection, self._data, self._filters + [(field, op, value)])
        
    def order_by(self, field: str, direction=None):
        return self
        
    def limit(self, count: int):
        return self
        
    async def get(self):
        # Simple mock - return empty results
        return []