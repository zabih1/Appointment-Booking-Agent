import re
import random
from datetime import datetime
import dateparser
import streamlit as st

def is_valid_email(email):
    """Validate email format."""
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(email_pattern, email))

def extract_appointment_details(response_text):
    """Extract appointment details from the LLM response."""
    details_pattern = r'<APPOINTMENT_DETAILS>(.*?)</APPOINTMENT_DETAILS>'
    match = re.search(details_pattern, response_text, re.DOTALL)
    
    if not match:
        return None, response_text.strip()
    
    details_text = match.group(1).strip()
    details = {}
    
    name_match = re.search(r'name:\s*(.*)', details_text)
    email_match = re.search(r'email:\s*(.*)', details_text)
    date_match = re.search(r'date:\s*(.*)', details_text)
    time_match = re.search(r'time:\s*(.*)', details_text)
    purpose_match = re.search(r'purpose:\s*(.*)', details_text)
    action_match = re.search(r'action:\s*(.*)', details_text)
    
    if name_match:
        details['name'] = name_match.group(1).strip()
    if email_match:
        details['email'] = email_match.group(1).strip()
        
    if date_match:
        date_str = date_match.group(1).strip()
        try:
            parsed_date = dateparser.parse(date_str)
            if parsed_date:
                details['date'] = parsed_date.strftime('%Y-%m-%d')
            else:
                for fmt in ['%m/%d/%Y', '%m-%d-%Y', '%Y-%m-%d', '%Y/%m/%d']:
                    try:
                        parsed_date = datetime.strptime(date_str, fmt)
                        details['date'] = parsed_date.strftime('%Y-%m-%d')
                        break
                    except ValueError:
                        continue
                if 'date' not in details:
                    details['date'] = date_str
        except Exception:
            details['date'] = date_str
    
    if time_match:
        time_str = time_match.group(1).strip()
        try:
            if ':' in time_str:
                hour, minute = map(int, time_str.split(':'))
                if 'am' not in time_str.lower() and 'pm' not in time_str.lower():
                    if hour == 0:
                        time_str = f"12:{minute:02d} AM"
                    elif hour < 12:
                        time_str = f"{hour}:{minute:02d} AM"
                    elif hour == 12:
                        time_str = f"12:{minute:02d} PM"
                    else:
                        time_str = f"{hour-12}:{minute:02d} PM"
            else:
                try:
                    hour = int(time_str.split()[0])
                    if "pm" in time_str.lower():
                        if hour < 12:
                            hour += 12
                    elif "am" in time_str.lower() and hour == 12:
                        hour = 0
                        
                    if hour == 0:
                        time_str = "12:00 AM"
                    elif hour < 12:
                        time_str = f"{hour}:00 AM"
                    elif hour == 12:
                        time_str = "12:00 PM"
                    else:
                        time_str = f"{hour-12}:00 PM"
                except:
                    pass
        except Exception:
            pass
        details['time'] = time_str
    
    if purpose_match:
        details['purpose'] = purpose_match.group(1).strip()
    if action_match:
        details['action'] = action_match.group(1).strip()
    
    clean_response = re.sub(details_pattern, '', response_text, flags=re.DOTALL).strip()
    
    return details, clean_response

def get_random_greeting():
    """Get a random greeting message for the chat bot."""
    greetings = [
        "👋 Hello there! I'm your friendly appointment booking assistant. How can I help you today?",
        "Hi! I'm here to help you book or check appointments. What can I do for you?",
        "Welcome! I'm your appointment assistant. Need to schedule something or check your bookings?",
        "Hello! I'm ready to help with your appointments. What would you like to do today?",
        "Hi there! Looking to book an appointment or check your schedule? I'm here to help!"
    ]
    return random.choice(greetings)