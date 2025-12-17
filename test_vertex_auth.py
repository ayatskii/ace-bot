#!/usr/bin/env python3
"""
Diagnostic script to test Vertex AI authentication and API access
"""
import os
import sys
from google.oauth2 import service_account
from google.auth.transport.requests import Request

def test_credentials():
    """Test if service account credentials are valid"""
    print("=" * 60)
    print("VERTEX AI AUTHENTICATION DIAGNOSTIC TOOL")
    print("=" * 60)
    print()
    
    # Check environment variable
    creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if not creds_path:
        creds_path = './service-account-key.json'
        print(f"⚠️  GOOGLE_APPLICATION_CREDENTIALS not set")
        print(f"    Using default: {creds_path}")
    else:
        print(f"✅ GOOGLE_APPLICATION_CREDENTIALS: {creds_path}")
    
    print()
    
    # Check if file exists
    if not os.path.exists(creds_path):
        print(f"❌ ERROR: Credentials file not found at: {creds_path}")
        return False
    
    print(f"✅ Credentials file exists ({os.path.getsize(creds_path)} bytes)")
    print()
    
    try:
        # Load credentials
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        
        print(f"✅ Service Account: {credentials.service_account_email}")
        print(f"✅ Project ID: {credentials.project_id}")
        print()
        
        # Try to refresh the token
        print("🔄 Testing token refresh...")
        request = Request()
        credentials.refresh(request)
        
        if credentials.token:
            print(f"✅ Token obtained successfully!")
            print(f"   Token (first 20 chars): {credentials.token[:20]}...")
            print()
            return True
        else:
            print("❌ Failed to obtain access token")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        print()
        print("POSSIBLE CAUSES:")
        print("1. Service account has been deleted or disabled")
        print("2. JSON file is corrupted")
        print("3. Network connectivity issues")
        return False

def test_vertex_ai():
    """Test Vertex AI API access"""
    print("=" * 60)
    print("TESTING VERTEX AI API ACCESS")
    print("=" * 60)
    print()
    
    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel
        
        project_id = "aceacademy-478613"
        location = "us-central1"
        
        print(f"Project: {project_id}")
        print(f"Location: {location}")
        print()
        
        print("🔄 Initializing Vertex AI...")
        vertexai.init(project=project_id, location=location)
        print("✅ Vertex AI initialized")
        print()
        
        print("🔄 Creating model instance...")
        model = GenerativeModel('gemini-2.0-flash-exp')
        print("✅ Model instance created")
        print()
        
        print("🔄 Testing simple generation...")
        response = model.generate_content("Say 'Hello, I am working!'")
        print(f"✅ Response: {response.text}")
        print()
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        print()
        print("POSSIBLE CAUSES:")
        print("1. Vertex AI API is NOT ENABLED for this project")
        print("2. Service account lacks 'Vertex AI User' role")
        print("3. Project billing is not set up")
        print("4. Invalid project ID or region")
        print()
        print("=" * 60)
        print("HOW TO FIX:")
        print("=" * 60)
        print()
        print("1. Enable Vertex AI API:")
        print("   https://console.cloud.google.com/apis/library/aiplatform.googleapis.com?project=aceacademy-478613")
        print()
        print("2. Grant permissions to service account:")
        print("   • Go to: https://console.cloud.google.com/iam-admin/iam?project=aceacademy-478613")
        print("   • Find: ace-bot-vertex-ai@aceacademy-478613.iam.gserviceaccount.com")
        print("   • Add role: 'Vertex AI User'")
        print()
        print("3. Enable billing:")
        print("   https://console.cloud.google.com/billing?project=aceacademy-478613")
        print()
        return False

if __name__ == "__main__":
    # Set credentials path
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.join(
        os.path.dirname(__file__), 
        'service-account-key.json'
    )
    
    # Run tests
    if test_credentials():
        print()
        test_vertex_ai()
    else:
        print("❌ Cannot proceed without valid credentials")
        sys.exit(1)
