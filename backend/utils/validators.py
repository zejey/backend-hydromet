"""
Validation utility functions
"""

import re


def normalize_phone_number(phone: str) -> str:
    """
    Normalize phone number to 09XXXXXXXXX format
    
    Examples:
        09123456789 -> 09123456789
        639123456789 -> 09123456789
        +639123456789 -> 09123456789
        9123456789 -> 09123456789
    """
    # Remove all non-digit characters
    phone = ''.join(filter(str.isdigit, phone))
    
    # Convert 63XXXXXXXXXX to 09XXXXXXXXX
    if phone.startswith('63') and len(phone) == 12:
        return '0' + phone[2:]
    
    # Convert 9XXXXXXXXX to 09XXXXXXXXX
    if phone.startswith('9') and len(phone) == 10:
        return '0' + phone
    
    # Already in correct format
    if phone.startswith('0') and len(phone) == 11:
        return phone
    
    # Return as is if format is unexpected
    return phone


def validate_phone_number(phone: str) -> bool:
    """
    Validate Philippine phone number format
    Must be 11 digits starting with 09
    """
    phone = normalize_phone_number(phone)
    return bool(re.match(r'^09\d{9}$', phone))


def format_phone_for_sms(phone: str) -> str:
    """
    Format phone number for SMS API (639XXXXXXXXX format)
    
    Examples:
        09123456789 -> 639123456789
    """
    phone = normalize_phone_number(phone)
    if phone.startswith('0'):
        return '63' + phone[1:]
    return phone