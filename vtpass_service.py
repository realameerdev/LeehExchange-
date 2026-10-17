"""
VTpass API service for telecom services
Handles airtime and data plan purchases
"""

import requests
import json
import logging
import os

# VTpass API configuration
VT_API_KEY = os.getenv("VT_API_KEY")
VT_PUBLIC_KEY = os.getenv("VT_PUBLIC_KEY")
VT_SECRET_KEY = os.getenv("VT_SECRET_KEY")
VT_BASE_URL = "https://sandbox.vtpass.com/api"

logger = logging.getLogger(__name__)

def get_vtpass_headers():
    """Get VTpass API headers"""
    return {
        'api-key': VT_API_KEY,
        'public-key': VT_PUBLIC_KEY,
        'secret-key': VT_SECRET_KEY,
        'Content-Type': 'application/json'
    }

def get_network_code(network_name):
    """Convert network name to VTpass service ID"""
    network_codes = {
        'MTN': 'mtn',
        'Airtel': 'airtel',
        'Glo': 'glo',
        '9mobile': 'etisalat'
    }
    return network_codes.get(network_name, 'mtn')

def get_data_plans(network):
    """Get available data plans for a network"""
    try:
        network_code = get_network_code(network)
        url = f"{VT_BASE_URL}/service-variations"
        params = {'serviceID': f'{network_code}-data'}
        
        response = requests.get(url, headers=get_vtpass_headers(), params=params)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('response_description') == '000':
                return data.get('content', {}).get('varations', [])
        
        logger.error(f"Failed to get data plans: {response.text}")
        return []
        
    except Exception as e:
        logger.error(f"Error getting data plans: {e}")
        return []

def calculate_data_price(size_mb):
    """Calculate data price based on size"""
    base_price = size_mb * 0.6
    if base_price >= 800:
        profit = 100
    elif base_price >= 500:
        profit = 70
    else:
        profit = 50
    
    return int(base_price + profit)

def verify_phone_number(phone, network):
    """Verify phone number with VTpass"""
    try:
        network_code = get_network_code(network)
        url = f"{VT_BASE_URL}/merchant-verify"
        
        payload = {
            'serviceID': network_code,
            'billersCode': phone
        }
        
        response = requests.post(
            url, 
            headers=get_vtpass_headers(), 
            json=payload
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get('response_description') == '000'
        
        return False
        
    except Exception as e:
        logger.error(f"Error verifying phone number: {e}")
        return False

def _vtpass_request(url, payload, max_retries=2):
    """Execute a VTpass POST with automatic retry on failure."""
    import time
    last_result = None
    for attempt in range(1 + max_retries):
        try:
            response = requests.post(url, headers=get_vtpass_headers(), json=payload, timeout=15)
            if response.status_code == 200:
                data = response.json()
                last_result = {
                    'success': data.get('response_description') == '000',
                    'message': data.get('content', {}).get('transactions', {}).get('status', 'Unknown'),
                    'transaction_id': data.get('requestId'),
                    'data': data
                }
                if last_result['success']:
                    return last_result
            else:
                last_result = {
                    'success': False,
                    'message': f"API Error: {response.status_code}",
                    'transaction_id': None,
                    'data': response.text
                }
        except Exception as e:
            logger.error(f"VTpass attempt {attempt + 1} failed: {e}")
            last_result = {
                'success': False,
                'message': f"Exception: {str(e)}",
                'transaction_id': None,
                'data': None
            }
        if attempt < max_retries:
            wait = 2 ** attempt
            logger.info(f"VTpass retry {attempt + 1}/{max_retries} in {wait}s …")
            time.sleep(wait)
    return last_result


def purchase_airtime(phone, amount, network, request_id):
    """Purchase airtime via VTpass API (auto-retry up to 2 times)."""
    network_code = get_network_code(network)
    url = f"{VT_BASE_URL}/pay"
    payload = {
        'request_id': request_id,
        'serviceID': network_code,
        'amount': amount,
        'phone': phone
    }
    result = _vtpass_request(url, payload)
    if not result['success']:
        logger.error(f"Airtime purchase failed after retries: {result['message']}")
    return result

def purchase_data(phone, variation_code, network, request_id):
    """Purchase data via VTpass API (auto-retry up to 2 times)."""
    network_code = get_network_code(network)
    url = f"{VT_BASE_URL}/pay"
    payload = {
        'request_id': request_id,
        'serviceID': f'{network_code}-data',
        'billersCode': phone,
        'variation_code': variation_code,
        'phone': phone
    }
    result = _vtpass_request(url, payload)
    if not result['success']:
        logger.error(f"Data purchase failed after retries: {result['message']}")
    return result

def format_data_plans_display(plans, network):
    """Format data plans for user display"""
    if not plans:
        return f"❌ No data plans available for {network}"
    
    message = f"📦 **Available {network} Data Plans:**\n\n"
    
    for i, plan in enumerate(plans[:10], 1):  # Limit to 10 plans
        name = plan.get('name', 'Unknown Plan')
        amount = plan.get('variation_amount', 0)
        code = plan.get('variation_code', '')
        
        message += f"{i}. **{name}** - ₦{amount}\n"
        message += f"   Code: `{code}`\n\n"
    
    return message