import re
import streamlit as st
from src.database import (
    get_appointments, 
    check_appointment_exists, 
    add_appointment, 
    delete_appointment, 
    get_table_structure
)
from src.utils import extract_appointment_details, is_valid_email
from src.llm_setup import format_appointment_response

def process_message(user_input, llm_chain, llm):
    """Process user messages and handle appointment-related actions."""
    try:
        # Extract email from input if present
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        email_match = re.search(email_pattern, user_input)
        if email_match:
            email = email_match.group()
            st.session_state['current_email'] = email
        
        # Check if input is a retrieval request
        user_input_lower = user_input.lower().strip()
        retrieval_phrases = ["retrieve", "check appointment", "my appointment", "show appointment", 
                            "view appointment", "get appointment", "find appointment", "look up", 
                            "lookup", "get info", "find info", "check info", "appointment info"]
        
        is_retrieval_request = any(phrase in user_input_lower for phrase in retrieval_phrases)
        
        # Direct retrieval flow
        if is_retrieval_request:
            email = st.session_state.get('current_email')
            
            if email:
                appointments = get_appointments(email=email)
                
                if appointments:
                    columns = get_table_structure()
                    response = f"Here are the appointments for {email}:\n\n"
                    for i, appt in enumerate(appointments):
                        appt_dict = {columns[j]: appt[j] for j in range(len(appt))}
                        response += f"📅 Appointment {i+1}:\n"
                        response += f"• Date: {appt_dict.get('date', 'N/A')}\n"
                        response += f"• Time: {appt_dict.get('time', 'N/A')}\n"
                        response += f"• Name: {appt_dict.get('name', 'N/A')}\n"
                        purpose = appt_dict.get('purpose', '')
                        if purpose and purpose not in ('N/A', 'None', 'none'):
                            response += f"• Purpose: {purpose}\n"
                        response += "\n"
                    return response.strip()
                else:
                    return f"I couldn't find any appointments associated with {email}. Would you like to book a new appointment?"
            else:
                return "To check your appointments, I'll need your email address. What email did you use when booking?"
        
        # Standard LLM processing flow
        llm_response = llm_chain.invoke({"input": user_input})
        
        response_text = ""
        if hasattr(llm_response, "text"):
            response_text = llm_response.text
        elif hasattr(llm_response, "content"):
            response_text = llm_response.content
        elif isinstance(llm_response, dict):
            response_text = llm_response.get("text", llm_response.get("content", ""))
        
        details, clean_response = extract_appointment_details(response_text)
        
        if details and details.get('email'):
            st.session_state['current_email'] = details['email']
            
        if details and details.get('name'):
            st.session_state['current_name'] = details['name']
            
        # Handle retrieval fallback with current email
        current_email = st.session_state.get('current_email')
        if current_email and is_retrieval_request and (not details or details.get('action') != 'retrieve'):
            appointments = get_appointments(email=current_email)
            
            if appointments:
                columns = get_table_structure()
                response = f"Here are the appointments for {current_email}:\n\n"
                for i, appt in enumerate(appointments):
                    appt_dict = {columns[j]: appt[j] for j in range(len(appt))}
                    response += f"📅 Appointment {i+1}:\n"
                    response += f"• Date: {appt_dict.get('date', 'N/A')}\n"
                    response += f"• Time: {appt_dict.get('time', 'N/A')}\n"
                    response += f"• Name: {appt_dict.get('name', 'N/A')}\n"
                    purpose = appt_dict.get('purpose', '')
                    if purpose and purpose not in ('N/A', 'None', 'none'):
                        response += f"• Purpose: {purpose}\n"
                    response += "\n"
                return response.strip()
            else:
                return f"I couldn't find any appointments associated with {current_email}. Would you like to book a new appointment?"
                
        # No details extracted
        if not details:
            return clean_response
        
        # Booking flow
        if details.get('action') == 'book':
            if not details.get('name'):
                details['name'] = st.session_state.get('current_name', '')
            if not details.get('email'):
                details['email'] = st.session_state.get('current_email', '')
            
            if not details.get('name'):
                return f"{clean_response}\n\nCould you please tell me your name?"
                
            if not details.get('email'):
                return f"{clean_response}\n\nThanks, {details['name']}! What's your email address?"
            elif not is_valid_email(details.get('email')):
                return f"{clean_response}\n\nThe email address doesn't seem valid. Could you please provide a valid email?"
                
            if not details.get('date'):
                return f"{clean_response}\n\nGreat! What date would you like to book? (Any format like 3/15/2025 or 2025-03-15 works)"
                
            if not details.get('time'):
                return f"{clean_response}\n\nPerfect! What time would you prefer on {details['date']}?"
                
            if not details.get('purpose') and 'purpose' not in details:
                return f"{clean_response}\n\nAlmost done! Could you tell me the purpose of this appointment?"
            
            # Save the current user info to session state
            st.session_state['current_name'] = details['name']
            st.session_state['current_email'] = details['email']
            
            # Check if appointment already exists
            if check_appointment_exists(details['name'], details['email'], details['date'], details['time']):
                return f"You already have an appointment on {details['date']} at {details['time']}. Would you like to book a different time?"
            
            # Add the appointment to the database
            purpose = details.get('purpose', 'General appointment')
            add_appointment(details['name'], details['email'], details['date'], details['time'], purpose)

            # Format and return confirmation
            confirmation = {
                "name": details['name'],
                "email": details['email'],
                "date": details['date'],
                "time": details['time'],
                "purpose": purpose
            }
            
            return format_appointment_response(confirmation, "confirmation", llm)
            
        # Retrieval flow
        elif details.get('action') == 'retrieve':
            email = details.get('email') or st.session_state.get('current_email', '')
            date = details.get('date')
            
            if not email:
                return f"{clean_response}\n\nPlease provide your email address so I can check your appointments."
            
            if email:
                st.session_state['current_email'] = email
            
            appointments = get_appointments(email=email, date=date)
            
            if appointments:
                columns = get_table_structure()
                response = f"Here are the appointments for {email}:\n\n"
                for i, appt in enumerate(appointments):
                    appt_dict = {columns[j]: appt[j] for j in range(len(appt))}
                    response += f"📅 Appointment {i+1}:\n"
                    response += f"• Date: {appt_dict.get('date', 'N/A')}\n"
                    response += f"• Time: {appt_dict.get('time', 'N/A')}\n"
                    response += f"• Name: {appt_dict.get('name', 'N/A')}\n"
                    purpose = appt_dict.get('purpose', '')
                    if purpose and purpose not in ('N/A', 'None', 'none'):
                        response += f"• Purpose: {purpose}\n"
                    response += "\n"
                return response.strip()
            else:
                return f"I couldn't find any appointments associated with {email}. Would you like to book a new appointment?"
        
        # Cancellation flow
        elif details.get('action') == 'cancel':
            appointments = []
            name = details.get('name') or st.session_state.get('current_name', '')
            email = details.get('email') or st.session_state.get('current_email', '')
            date = details.get('date')
            
            if not name and not email:
                return f"{clean_response}\n\nPlease provide your name or email so I can find and cancel your appointment."
            
            if name:
                st.session_state['current_name'] = name
            if email:
                st.session_state['current_email'] = email
                
            appointments = get_appointments(name, email, date)
            
            if not appointments:
                return f"I couldn't find any appointments to cancel. Please check your details and try again."
            
            if len(appointments) == 1:
                columns = get_table_structure()
                appt_dict = {columns[j]: appointments[0][j] for j in range(len(appointments[0]))}
                appt_id = appt_dict.get('id')
                appt_date = appt_dict.get('date')
                appt_time = appt_dict.get('time')
                
                if delete_appointment(appt_id):
                    return f"✅ I've successfully canceled your appointment on {appt_date} at {appt_time}. Is there anything else I can help you with?"
                else:
                    return f"❌ I encountered an error while trying to cancel your appointment. Please try again or contact support."
            
            columns = get_table_structure()
            appointments_text = "I found multiple appointments. Please specify which one you'd like to cancel by ID:\n\n"
            for i, appt in enumerate(appointments):
                appt_dict = {columns[j]: appt[j] for j in range(len(appt))}
                appointments_text += f"📅 Appointment {i+1}:\n"
                appointments_text += f"• ID: {appt_dict.get('id', 'N/A')}\n"
                appointments_text += f"• Date: {appt_dict.get('date', 'N/A')}\n"
                appointments_text += f"• Time: {appt_dict.get('time', 'N/A')}\n"
                appointments_text += f"• Purpose: {appt_dict.get('purpose', 'General appointment')}\n\n"
            
            appointments_text += "Please reply with the ID number of the appointment you want to cancel (e.g., 'Cancel appointment ID 5')."
            return appointments_text
            
        return clean_response
    
    except Exception as e:
        return f"Error processing message: {str(e)}\n\nPlease try again or restart the application."