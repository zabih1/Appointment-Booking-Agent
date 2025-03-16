import streamlit as st
import sqlite3
import datetime
import re
import os
from datetime import datetime, timedelta
import dateparser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from langchain.schema import HumanMessage, AIMessage
from langchain.chains import LLMChain

# Database setup
def init_db():
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    
    # Check if the table exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='appointments'")
    table_exists = c.fetchone()
    
    if table_exists:
        # Check if email column exists
        try:
            c.execute("SELECT email FROM appointments LIMIT 1")
        except sqlite3.OperationalError:
            # Add email column if it doesn't exist
            st.write("Adding email column to existing database...")
            c.execute("ALTER TABLE appointments ADD COLUMN email TEXT DEFAULT 'no-email@example.com'")
            conn.commit()
    else:
        # Create new table with email column
        c.execute('''
        CREATE TABLE appointments
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         name TEXT NOT NULL,
         email TEXT NOT NULL,
         date TEXT NOT NULL,
         time TEXT NOT NULL,
         purpose TEXT,
         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
        ''')
        conn.commit()
    
    conn.close()





def check_appointment_exists(name, email, date, time):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM appointments WHERE name = ? AND email = ? AND date = ? AND time = ?", 
            (name, email, date, time))
    result = c.fetchone()
    
    conn.close()
    return result is not None

# Setup the LLM
def setup_llm():
    # Get the API key from Streamlit secrets or environment variable
    api_key = os.environ.get('GEMINI_API_KEY') or st.secrets.get('GEMINI_API_KEY', '')
    
    if not api_key:
        st.error("Google API key not found. Please set it in your environment variables or Streamlit secrets.")
        st.stop()
    
    # Initialize the Google Generative AI model
    llm = ChatGoogleGenerativeAI(
        api_key=api_key,
        model="gemini-2.0-flash"
    )
    
    # Create a prompt template
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an appointment booking assistant. Your task is to:
        1. Help users book appointments by extracting name, email, date, time, and purpose.
        2. Help users retrieve their appointment information.
        3. Respond in a friendly and helpful manner.
        
        Important: Email address is required for all appointments. Always ask for it if not provided.
        
        When you identify appointment details, format your response with JSON-like tags:
         
        <APPOINTMENT_DETAILS>
        name: [extracted name]
        email: [extracted email]
        date: [extracted date in YYYY-MM-DD format]
        time: [extracted time in HH:MM format]
        purpose: [extracted purpose]
        action: [book/retrieve]
        </APPOINTMENT_DETAILS>
        
        If details are missing, indicate what information is needed but don't include the tags."""),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}")
    ])
    
    # Create memory
    memory = ConversationBufferMemory(return_messages=True, input_key="input", memory_key="history")
    
    # Create chain
    chain = LLMChain(
        llm=llm,
        prompt=prompt,
        memory=memory
    )
    
    return chain, llm


# Generate a message using the LLM for a specific purpose
def generate_llm_message(llm, prompt_text):
    try:
        return llm.invoke(prompt_text).content
    except Exception as e:
        st.warning(f"Failed to generate message with LLM: {str(e)}")
        return None

# Helper function to validate email format
def is_valid_email(email):
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(email_pattern, email))

# Get the table structure to determine column order
def get_table_structure():
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("PRAGMA table_info(appointments)")
    columns = c.fetchall()
    conn.close()
    return [col[1] for col in columns]

# Format appointment data for display
def format_appointments(appointments, clean_response, llm):
    if not appointments:
        return f"{clean_response}\n\nYou don't have any appointments scheduled."
    
    # Prepare appointment data for the LLM
    appointments_info = []
    columns = get_table_structure()
    
    for appt in appointments:
        appt_dict = {columns[i]: appt[i] for i in range(len(appt)) if i < len(columns)}
        appointments_info.append({
            'date': appt_dict.get('date', 'N/A'),
            'time': appt_dict.get('time', 'N/A'),
            'name': appt_dict.get('name', 'N/A'),
            'email': appt_dict.get('email', 'N/A'),
            'purpose': appt_dict.get('purpose', 'N/A')
        })
    
    # Ask the LLM to format the appointment list
    appointments_text = "\n".join([
        f"Appointment {i+1}:\n" +
        f"- Date: {appt['date']}\n" +
        f"- Time: {appt['time']}\n" +
        f"- Name: {appt['name']}\n" +
        f"- Email: {appt['email']}\n" +
        f"- Purpose: {appt['purpose']}"
        for i, appt in enumerate(appointments_info)
    ])
    
    appointments_prompt = f"""
    The user has asked to retrieve their appointment information.
    
    Here are the appointments found in our system:
    
    {appointments_text}
    
    Please format this information in a friendly, easy-to-read way to present back to the user.
    """
    
    formatted_appointments = generate_llm_message(llm, appointments_prompt)
    
    if formatted_appointments:
        return f"{clean_response}\n\n{formatted_appointments}"
    

# Chatbot logic
def process_message(user_input, llm_chain, llm):
    try:
        # Get response from the LLM
        llm_response = llm_chain.invoke({"input": user_input})
        response_text = llm_response["text"]
        
        # Extract appointment details from the LLM response
        details, clean_response = extract_appointment_details(response_text)
        
        if not details:
            return clean_response
        
        # Process based on action
        if details.get('action') == 'book':
            # Check if we have all necessary details
            if not details.get('name'):
                details['name'] = st.session_state.get('current_name', '')
            if not details.get('email'):
                details['email'] = st.session_state.get('current_email', '')
            
            # Check for missing information
            missing = []
            if not details.get('name'):
                missing.append("name")
            if not details.get('email'):
                missing.append("email")
            elif not is_valid_email(details.get('email')):
                return f"{clean_response}\n\nThe email address provided doesn't seem to be valid. Please provide a valid email address."
            if not details.get('date'):
                missing.append("date")
            if not details.get('time'):
                missing.append("time")
                
            if missing:
                return f"{clean_response}\n\nI still need your {', '.join(missing)} to book the appointment."
            
            # Check if appointment exists
            if check_appointment_exists(details['name'], details['email'], details['date'], details['time']):
                return f"You already have an appointment on {details['date']} at {details['time']}. Would you like to book a different time?"
            
            # Book the appointment
            purpose = details.get('purpose', 'General appointment')
            add_appointment(details['name'], details['email'], details['date'], details['time'], purpose)
            st.session_state['current_name'] = details['name']
            st.session_state['current_email'] = details['email']

            # Generate a confirmation message
            prompt = f"""
            Based on our conversation, I've booked an appointment with the following details:
            - Name: {details['name']}
            - Email: {details['email']}
            - Date: {details['date']}
            - Time: {details['time']}
            - Purpose: {details.get('purpose', 'General appointment')}
            
            Please format this information in a friendly, easy-to-read way to present back to the user.
            """
            
            confirmation = generate_llm_message(llm, prompt)
            if confirmation:
                return f"{clean_response}\n\n{confirmation}"

        
        elif details.get('action') == 'retrieve':
            # Get name and email for retrieval
            name = details.get('name') or st.session_state.get('current_name', '')
            email = details.get('email') or st.session_state.get('current_email', '')
            date = details.get('date')
            
            # Check if we have at least name or email
            if not name and not email:
                return f"{clean_response}\n\nPlease provide your name or email so I can check your appointments."
            
            # Update session state
            if name:
                st.session_state['current_name'] = name
            if email:
                st.session_state['current_email'] = email
            
            # Get appointments
            appointments = get_appointments(name, email, date)
            
            # Format and return appointments
            return format_appointments(appointments, clean_response, llm)
            
        # Default response if no action is determined but details were found
        return clean_response
    
    except Exception as e:
        return f"Error processing message: {str(e)}\n\nPlease try again or restart the application."

# Initialize the app
def main():
    st.set_page_config(page_title="AI Appointment Booking Agent", page_icon="📅")
    
    if 'messages' not in st.session_state:
        st.session_state['messages'] = [{"role": "assistant", "content": "Hello! I'm your AI appointment booking assistant. How can I help you today? I can help you book appointments or check your existing ones. Please provide your name and email when booking."}]
    
    if 'current_name' not in st.session_state:
        st.session_state['current_name'] = None
        
    if 'current_email' not in st.session_state:
        st.session_state['current_email'] = None
        
    if 'llm_chain' not in st.session_state:
        try:
            # Initialize LLM chain and store in session state
            st.session_state['llm_chain'], st.session_state['llm'] = setup_llm()
        except Exception as e:
            st.error(f"Error initializing LLM: {str(e)}")
            st.error("Please make sure you have set the GOOGLE_API_KEY environment variable or added it to Streamlit secrets.")
            st.stop()
    
    st.title("AI Appointment Booking Agent")
    
    # Initialize database
    try:
        init_db()
    except Exception as e:
        st.error(f"Database initialization error: {str(e)}")
        if os.path.exists('appointments.db'):
            st.error("The database file exists but there might be a schema issue. You may need to delete the file and restart.")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    
    # User input
    user_input = st.chat_input("Type your message here...")
    
    if user_input:
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)
        
        # Generate response using the LLM chain
        response = process_message(user_input, st.session_state['llm_chain'], st.session_state['llm'])
        
        # Add assistant response to chat history
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.write(response)

if __name__ == "__main__":
    main()
