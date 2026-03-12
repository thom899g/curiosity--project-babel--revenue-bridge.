"""
Firebase configuration and initialization.
Centralized state management for the entire Project Babel ecosystem.
"""
import os
import json
import logging
from typing import Optional, Dict, Any
from google.cloud import firestore
from google.oauth2 import service_account
from dataclasses import dataclass, asdict
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

logger = logging.getLogger(__name__)

@dataclass
class Protocol:
    """Data model for DeFi protocol tracking"""
    id: Optional[str] = None
    name: str = ""
    github_url: str = ""
    website: str = ""
    last_analyzed: Optional[datetime] = None
    risk_score: float = 0.0
    tags: list = None
    qualification_status: str = "pending"  # pending, qualified, rejected
    rejection_reason: str = ""
    created_at: datetime = None
    tvl_indicator: bool = False
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.created_at is None:
            self.created_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Firestore-serializable dict"""
        data = asdict(self)
        if self.id:
            data.pop('id')
        # Convert datetime objects to Firestore timestamps
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value
        return data

class FirebaseManager:
    """Singleton manager for Firebase operations with error handling"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._initialize_firebase()
            self._initialized = True
    
    def _initialize_firebase(self):
        """Initialize Firebase with service account credentials"""
        try:
            # Check for service account key in multiple locations
            key_paths = [
                'serviceAccountKey.json',
                '/etc/secrets/serviceAccountKey.json',
                os.path.expanduser('~/.config/babel/serviceAccountKey.json')
            ]
            
            cred = None
            for path in key_paths:
                if os.path.exists(path):
                    logger.info(f"Found Firebase credentials at {path}")
                    cred = credentials.Certificate(path)
                    break
            
            if cred is None:
                logger.error("No Firebase service account key found")
                raise FileNotFoundError(
                    "Firebase service account key not found. "
                    "Please place serviceAccountKey.json in one of: " + ", ".join(key_paths)
                )
            
            # Initialize only if not already initialized
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            
            self.db = firestore.client()
            logger.info("Firebase initialized successfully")
            
        except Exception as e:
            logger.error(f"Firebase initialization failed: {str(e)}")
            raise
    
    def create_protocol(self, protocol: Protocol) -> str:
        """Create a new protocol document with error handling"""
        try:
            # Validate required fields
            if not protocol.github_url:
                raise ValueError("github_url is required")
            
            protocol.created_at = datetime.utcnow()
            data = protocol.to_dict()
            
            # Add to Firestore
            doc_ref = self.db.collection('protocols').document()
            doc_ref.set(data)
            
            protocol_id = doc_ref.id
            logger.info(f"Created protocol {protocol_id}: {protocol.name}")
            return protocol_id
            
        except Exception as e:
            logger.error(f"Failed to create protocol: {str(e)}")
            raise
    
    def update_protocol(self, protocol_id: str, updates: Dict[str, Any]) -> bool:
        """Update protocol document with error handling"""
        try:
            doc_ref = self.db.collection('protocols').document(protocol_id)
            doc_ref.update(updates)
            logger.info(f"Updated protocol {protocol_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update protocol {protocol_id}: {str(e)}")
            return False
    
    def get_protocol(self, protocol_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve protocol document with error handling"""
        try:
            doc = self.db.collection('protocols').document(protocol_id).get()
            if doc.exists:
                return {**doc.to_dict(), 'id': doc.id}
            return None
        except Exception as e:
            logger.error(f"Failed to get protocol {protocol_id}: {str(e)}")
            return None

# Global instance
firebase_manager = FirebaseManager()