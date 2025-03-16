import streamlit as st
import os
import re
from dotenv import load_dotenv
from src.database import init_db, get_appointments, DB_FOLDER, DB_NAME, DB_PATH
from src.llm_setup import setup_llm
from src.appointment_handler import process_message
from src.utils import get_random_greeting

# Load environment variables
load_dotenv()

def main():
    st.set_page_config(page_title="AI Appointment Booking Agent", page_icon="📅")

    # Initialize session state variables
    if 'messages' not in st.session_state:
        st.session_state['messages'] = [{"role": "assistant", "content": get_random_greeting()}]

    if 'current_name' not in st.session_state:
        st.session_state['current_name'] = None
        
    if 'current_email' not in st.session_state:
        st.session_state['current_email'] = None
        
        
    # Initialize LLM chain
    if 'llm_chain' not in st.session_state:
        try:
            st.session_state['llm_chain'], st.session_state['llm'] = setup_llm()
        except Exception as e:
            st.error(f"Error initializing LLM: {str(e)}")
            st.error("Please make sure you have set the GEMINI_API_KEY environment variable or added it to .env file.")
            st.stop()
    
    # Page title
    st.title("📅 AI Appointment Booking Agent")
    
    # Initialize database
    try:
        init_db()
    except Exception as e:
        st.error(f"Database initialization error: {str(e)}")
        if os.path.exists(DB_PATH):
            st.error(f"The database file exists at {DB_PATH} but there might be a schema issue. You may need to delete the file and restart.")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # Chat input
    user_input = st.chat_input("Type your message here...")
    
    if user_input:
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)
        
        # Extract email from input
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        email_match = re.search(email_pattern, user_input)
        
        if email_match:
            email = email_match.group()
            if not st.session_state.get('current_email') or st.session_state.get('current_email') != email:
                st.session_state['current_email'] = email
                
                # Direct retrieval if only email was provided
                if len(user_input.strip()) < 50 and email in user_input:
                    appointments = get_appointments(email=email)
                    
                    if appointments:
                        from src.database import get_table_structure
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
                        
                        st.session_state.messages.append({"role": "assistant", "content": response})
                        with st.chat_message("assistant"):
                            st.write(response)
                        st.stop()
        
        # Process the message
        response = process_message(user_input, st.session_state['llm_chain'], st.session_state['llm'])
        
        # Add assistant response to chat history
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.write(response)
            


if __name__ == "__main__":
    main()