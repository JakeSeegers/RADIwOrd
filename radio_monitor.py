import streamlit as st
import requests
import json
import hmac
import hashlib
import base64
import time
import threading
from datetime import datetime
import pandas as pd

# Page config
st.set_page_config(
    page_title="📻 Radio Monitor",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Try to import OpenAI safely
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Default configuration
DEFAULT_CONFIG = {
    'api_key': 'otL35tw40MzbfjbNRNApY8JggubKsqV1',
    'api_key_id': '79beb9f',
    'app_id': '6818aff92e1ce',
    'username': 'yotaxi1042',
    'password': 'yotaxi1042@avulos.com',
    'whisper_model': 'whisper-1',
    'min_duration': 2,
    'poll_interval': 5,
    'keywords': ['ice', 'immigration', 'federal', 'detain', 'dpss', 'gunshot', 'shots fired', 'officer down'],
    'openai_api_key': ''
}

# Initialize session state
def init_session_state():
    defaults = {
        'monitor_running': False,
        'discovered_channels': {},
        'selected_channels': [],
        'transcripts': [],
        'monitor_stats': {
            "calls_received": 0,
            "calls_processed": 0,
            "keywords_found": 0
        },
        'user_token': None,
        'user_id': None,
        'monitor_thread': None,
        'stop_event': None,
        **DEFAULT_CONFIG
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

class RadioMonitorAPI:
    """Handle Broadcastify API interactions"""
    
    def __init__(self):
        self.base_url = "https://api.bcfy.io"
    
    def generate_jwt(self, include_user_auth=False):
        """Generate JWT token for API authentication"""
        try:
            header = {
                "alg": "HS256",
                "typ": "JWT",
                "kid": st.session_state.api_key_id
            }
            
            current_time = int(time.time())
            payload = {
                "iss": st.session_state.app_id,
                "iat": current_time,
                "exp": current_time + 3600
            }
            
            if include_user_auth and st.session_state.user_token and st.session_state.user_id:
                payload["sub"] = int(st.session_state.user_id)
                payload["utk"] = st.session_state.user_token
            
            # Encode header and payload
            header_encoded = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
            payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
            
            # Create signature
            message = f"{header_encoded}.{payload_encoded}"
            signature = hmac.new(
                st.session_state.api_key.encode(),
                message.encode(),
                hashlib.sha256
            ).digest()
            signature_encoded = base64.urlsafe_b64encode(signature).decode().rstrip('=')
            
            return f"{message}.{signature_encoded}"
        
        except Exception as e:
            st.error(f"JWT generation error: {e}")
            return None
    
    def authenticate_user(self):
        """Authenticate user and get token"""
        try:
            jwt_token = self.generate_jwt()
            if not jwt_token:
                return False
            
            headers = {"Authorization": f"Bearer {jwt_token}"}
            data = {
                "username": st.session_state.username,
                "password": st.session_state.password
            }
            
            response = requests.post(f"{self.base_url}/common/v1/auth", headers=headers, data=data)
            
            if response.status_code == 200:
                auth_data = response.json()
                st.session_state.user_token = auth_data.get('token')
                st.session_state.user_id = auth_data.get('uid')
                return True
            else:
                st.error(f"Authentication failed: {response.status_code}")
                return False
        
        except Exception as e:
            st.error(f"Authentication error: {e}")
            return False
    
    def discover_county_channels(self, county_id):
        """Discover channels by county - debug version"""
        try:
            jwt_token = self.generate_jwt()
            if not jwt_token:
                st.error("Failed to generate JWT token")
                return {}
            
            headers = {"Authorization": f"Bearer {jwt_token}"}
            
            # The documented endpoint from your docs
            url = f"{self.base_url}/calls/v1/groups_county/{county_id}"
            
            st.info(f"🔍 Trying: {url}")
            st.info(f"📋 Headers: Authorization: Bearer {jwt_token[:20]}...")
            
            response = requests.get(url, headers=headers)
            
            st.info(f"📊 Response Status: {response.status_code}")
            st.info(f"📄 Response Headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                data = response.json()
                st.success(f"✅ Success! Raw response:")
                st.json(data)
                
                discovered = {}
                
                # Handle the response
                if isinstance(data, dict):
                    groups = data.get('groups', [])
                    for group in groups:
                        if isinstance(group, dict):
                            group_id = group.get('groupId') or group.get('id')
                            description = group.get('description') or group.get('descr') or group.get('name', 'Unknown')
                            if group_id:
                                discovered[str(group_id)] = description
                
                elif isinstance(data, list):
                    for group in data:
                        if isinstance(group, dict):
                            group_id = group.get('groupId') or group.get('id')
                            description = group.get('description') or group.get('descr') or group.get('name', 'Unknown')
                            if group_id:
                                discovered[str(group_id)] = description
                
                return discovered
            
            elif response.status_code == 401:
                st.error("❌ Authentication failed - JWT token issue")
                st.info("Try refreshing your credentials in Settings")
                
            elif response.status_code == 404:
                st.warning(f"❌ County {county_id} not found or no groups available")
                st.info("This could mean:")
                st.markdown("""
                - County ID is correct but no Broadcastify Calls coverage
                - County ID format might be wrong
                - No active groups in the last 30 days
                """)
                
            else:
                st.error(f"❌ Unexpected response: {response.status_code}")
                try:
                    error_data = response.json()
                    st.json(error_data)
                except:
                    st.text(response.text)
            
            return {}
        
        except Exception as e:
            st.error(f"Discovery error: {e}")
            return {}
    
    def test_all_endpoints(self):
        """Test what endpoints actually exist"""
        jwt_token = self.generate_jwt()
        if not jwt_token:
            return
        
        headers = {"Authorization": f"Bearer {jwt_token}"}
        
        # Test various endpoints to see what works
        test_endpoints = [
            "/calls/v1/playlists_public",
            "/calls/v1/groups_county/741",  # Indianapolis
            "/calls/v1/county_groups/741",
            "/calls/v1/playlists_county/741",
        ]
        
        st.subheader("🔬 API Endpoint Testing")
        
        for endpoint in test_endpoints:
            try:
                url = f"{self.base_url}{endpoint}"
                response = requests.get(url, headers=headers)
                
                if response.status_code == 200:
                    st.success(f"✅ {endpoint} - Works!")
                    data = response.json()
                    if isinstance(data, list):
                        st.info(f"Returns list with {len(data)} items")
                    elif isinstance(data, dict):
                        st.info(f"Returns dict with keys: {list(data.keys())}")
                elif resp
