import streamlit as st
import sqlite3
import re
import os
from datetime import datetime
import dateparser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from langchain.chains import LLMChain
import random
from dotenv import load_dotenv
load_dotenv()

def init_db():
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='appointments'")
    table_exists = c.fetchone()
    
    if table_exists:
        try:
            c.execute("SELECT email FROM appointments LIMIT 1")
        except sqlite3.OperationalError:
            st.write("Adding email column to existing database...")
            c.execute("ALTER TABLE appointments ADD COLUMN email TEXT DEFAULT 'no-email@example.com'")
            conn.commit()
    else:
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

def add_appointment(name, email, date, time, purpose):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("INSERT INTO appointments (name, email, date, time, purpose) VALUES (?, ?, ?, ?, ?)",
              (name, email, date, time, purpose))
    conn.commit()
    conn.close()

def get_appointments(name=None, email=None, date=None):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    
    query = "SELECT * FROM appointments"
    params = []
    
    conditions = []
    if name:
        conditions.append("LOWER(name) LIKE LOWER(?)")
        params.append(f"%{name}%")
    if email:
        conditions.append("LOWER(email) LIKE LOWER(?)")
        params.append(f"%{email}%")
    if date:
        conditions.append("date = ?")
        params.append(date)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY date, time"
    
    if 'debug_log' not in st.session_state:
        st.session_state['debug_log'] = ""
    st.session_state['debug_log'] += f"\nExecuting SQL: {query} with params {params}"
    
    c.execute(query, params)
    appointments = c.fetchall()
    
    st.session_state['debug_log'] += f"\nFound {len(appointments)} appointments"
    
    conn.close()
    return appointments

def check_appointment_exists(name, email, date, time):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM appointments WHERE name = ? AND email = ? AND date = ? AND time = ?", 
            (name, email, date, time))
    result = c.fetchone()
    
    conn.close()
    return result is not None

def delete_appointment(id):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("DELETE FROM appointments WHERE id = ?", (id,))
    rows_affected = conn.total_changes
    conn.commit()
    conn.close()
    return rows_affected > 0

def get_table_structure():
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("PRAGMA table_info(appointments)")
    columns = c.fetchall()
    conn.close()
    return [col[1] for col in columns]

def setup_llm():
    api_key = os.getenv('GEMINI_API_KEY')
    
    if not api_key:
        st.error("Google API key not found. Please set the GEMINI_API_KEY in your environment variables or .env file.")
        st.stop()
    
    try:
        llm = ChatGoogleGenerativeAI(
            api_key=api_key,
            model="gemini-2.0-flash"
        )
    except Exception as e:
        st.warning(f"Error initializing gemini-2.0-flash: {str(e)}")
        st.warning("Falling back to gemini-pro model.")
        llm = ChatGoogleGenerativeAI(
            api_key=api_key,
            model="gemini-pro"
        )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a friendly and helpful appointment booking assistant named AppointmentBot. Your job is to:
            1. Help users book appointments by collecting their information in a natural, conversational way.
            2. Ask for information one piece at a time - don't ask for multiple pieces of information in a single message.
            3. First ask for their name, then email, then preferred date, then time, and finally the purpose of their appointment.
            4. Help users retrieve their existing appointment information when they ask about their appointments.
            5. Help users cancel appointments if requested.
            6. Always use a warm, friendly tone with some appropriate emojis.

            Important: Email address is required for all appointments. Always ask for it if not provided.

            When you identify appointment details, format your response with JSON-like tags:
            
            <APPOINTMENT_DETAILS>
            name: [extracted name]
            email: [extracted email]
            date: [extracted date in YYYY-MM-DD format]
            time: [extracted time in 12-hour format with AM/PM]
            purpose: [extracted purpose]
            action: [book/retrieve/cancel]
            </APPOINTMENT_DETAILS>

            When displaying appointments, use a friendly, conversational format with emojis.

            The initial greeting should be varied and personalized, not the same message every time.
            """),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}")
    ])
    
    memory = ConversationBufferMemory(return_messages=True, input_key="input", memory_key="history")
    
    chain = LLMChain(
        llm=llm,
        prompt=prompt,
        memory=memory
    )
    
    return chain, llm

def is_valid_email(email):
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(email_pattern, email))

def extract_appointment_details(response_text):
    if 'debug_log' in st.session_state:
        st.session_state['debug_log'] += f"\n\nModel response: {response_text[:100]}..." if response_text else "\nEmpty model response"
    
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

def format_appointment_response(data, response_type, llm, clean_response=None):
    if response_type == "retrieval" and isinstance(data, list):
        st.session_state['debug_log'] = f"Retrieved {len(data)} appointments" if 'debug_log' not in st.session_state else st.session_state['debug_log'] + f"\nRetrieved {len(data)} appointments"
    try:
        if response_type == "confirmation":
            system_message = """You are a helpful assistant that formats appointment confirmations in a conversational way. 
            Use bullet points with relevant emojis. Never invent information - only use what's provided. 
            Start with a positive confirmation like 'Great! I've booked your appointment successfully! 📝' 
            End with 'Your appointment is all set! Is there anything else you'd like help with?'"""
            prompt_input = "Please format this appointment confirmation naturally:\n{data}"
        else:
            if not data:
                return f"{clean_response}\n\nYou don't have any appointments scheduled."
                
            system_message = """You are a helpful assistant that formats appointment data in a friendly, conversational way.
            Use bullet points with relevant emojis. Never invent information - only use what's provided."""
            prompt_input = """Please format these appointments naturally. Start with "Here are your appointments:" 

Appointment Data:
{data}"""

        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", prompt_input)
        ])
        
        chain = prompt_template | llm
        formatted_response = chain.invoke({"data": data}).content
        
        if response_type == "retrieval" and clean_response:
            return f"{clean_response}\n\n{formatted_response}"
        return formatted_response
        
    except Exception as e:
        if response_type == "confirmation":
            details = data
            return f"""Great! I've booked your appointment successfully! 📝

Here are the details:
- Name: {details['name']}
- Email: {details['email']}
- Date: {details['date']}
- Time: {details['time']}
- Purpose: {details.get('purpose', 'General appointment')}

Your appointment is all set! Is there anything else you'd like help with?"""
        else:
            appointments = data
            columns = get_table_structure()
            appointments_text = "Here are your appointments:\n\n"
            for i, appt in enumerate(appointments):
                appt_dict = {columns[j]: appt[j] for j in range(len(appt))}
                appointments_text += f"📅 Appointment {i+1}:\n"
                appointments_text += f"• ID: {appt_dict.get('id', 'N/A')}\n"
                appointments_text += f"• Date: {appt_dict.get('date', 'N/A')}\n"
                appointments_text += f"• Time: {appt_dict.get('time', 'N/A')}\n"
                appointments_text += f"• Name: {appt_dict.get('name', 'N/A')}\n"
                purpose = appt_dict.get('purpose', '')
                if purpose and purpose.lower() not in ('n/a', 'none'):
                    appointments_text += f"• Purpose: {purpose}\n"
                appointments_text += "\n"
            
            if clean_response:
                return f"{clean_response}\n\n{appointments_text.strip()}"
            return appointments_text.strip()

def process_message(user_input, llm_chain, llm):
    try:
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        email_match = re.search(email_pattern, user_input)
        if email_match:
            email = email_match.group()
            st.session_state['current_email'] = email
            st.session_state['debug_log'] += f"\nExtracted email from input: {email}"
        
        user_input_lower = user_input.lower().strip()
        retrieval_phrases = ["retrieve", "check appointment", "my appointment", "show appointment", 
                            "view appointment", "get appointment", "find appointment", "look up", 
                            "lookup", "get info", "find info", "check info", "appointment info"]
        
        is_retrieval_request = any(phrase in user_input_lower for phrase in retrieval_phrases)
        
        if is_retrieval_request:
            st.session_state['debug_log'] += f"\nDetected retrieval request: {user_input}"
            
            email = st.session_state.get('current_email')
            
            if email:
                st.session_state['debug_log'] += f"\nDirect retrieval with email: {email}"
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
        
        llm_response = llm_chain.invoke({"input": user_input})
        
        response_text = ""
        if hasattr(llm_response, "text"):
            response_text = llm_response.text
        elif hasattr(llm_response, "content"):
            response_text = llm_response.content
        elif isinstance(llm_response, dict):
            response_text = llm_response.get("text", llm_response.get("content", ""))
            
        st.session_state['debug_log'] += f"\nModel response: {response_text[:100]}..." if response_text else "\nEmpty model response"
        
        details, clean_response = extract_appointment_details(response_text)
        
        if details and details.get('email'):
            st.session_state['current_email'] = details['email']
            
        if details and details.get('name'):
            st.session_state['current_name'] = details['name']
            
        current_email = st.session_state.get('current_email')
        if current_email and is_retrieval_request and (not details or details.get('action') != 'retrieve'):
            st.session_state['debug_log'] += f"\nOverriding with direct retrieval for {current_email}"
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
                
        if not details:
            return clean_response
        
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
            
            st.session_state['current_name'] = details['name']
            st.session_state['current_email'] = details['email']
            
            if check_appointment_exists(details['name'], details['email'], details['date'], details['time']):
                return f"You already have an appointment on {details['date']} at {details['time']}. Would you like to book a different time?"
            
            purpose = details.get('purpose', 'General appointment')
            add_appointment(details['name'], details['email'], details['date'], details['time'], purpose)

            confirmation = {
                "name": details['name'],
                "email": details['email'],
                "date": details['date'],
                "time": details['time'],
                "purpose": purpose
            }
            
            return format_appointment_response(confirmation, "confirmation", llm)
            
        elif details.get('action') == 'retrieve':
            email = details.get('email') or st.session_state.get('current_email', '')
            date = details.get('date')
            
            if not email:
                return f"{clean_response}\n\nPlease provide your email address so I can check your appointments."
            
            if email:
                st.session_state['current_email'] = email
            
            appointments = get_appointments(email=email, date=date)
            st.session_state['debug_log'] += f"\nDirect retrieval in 'retrieve' action with email: {email}"
            
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

def get_random_greeting():
    greetings = [
        "👋 Hello there! I'm your friendly appointment booking assistant. How can I help you today?",
        "Hi! I'm here to help you book or check appointments. What can I do for you?",
        "Welcome! I'm your appointment assistant. Need to schedule something or check your bookings?",
        "Hello! I'm ready to help with your appointments. What would you like to do today?",
        "Hi there! Looking to book an appointment or check your schedule? I'm here to help!"
    ]
    return random.choice(greetings)

def main():
    st.set_page_config(page_title="AI Appointment Booking Agent", page_icon="📅")

    if 'messages' not in st.session_state:
        st.session_state['messages'] = [{"role": "assistant", "content": get_random_greeting()}]

    if 'current_name' not in st.session_state:
        st.session_state['current_name'] = None
        
    if 'current_email' not in st.session_state:
        st.session_state['current_email'] = None
        
    if 'debug_log' not in st.session_state:
        st.session_state['debug_log'] = ""
        
    if 'show_debug' not in st.session_state:
        st.session_state['show_debug'] = False
        
    if 'llm_chain' not in st.session_state:
        try:
            st.session_state['llm_chain'], st.session_state['llm'] = setup_llm()
        except Exception as e:
            st.error(f"Error initializing LLM: {str(e)}")
            st.error("Please make sure you have set the GEMINI_API_KEY environment variable or added it to .env file.")
            st.stop()
    
    st.title("📅 AI Appointment Booking Agent")
    
    try:
        init_db()
    except Exception as e:
        st.error(f"Database initialization error: {str(e)}")
        if os.path.exists('appointments.db'):
            st.error("The database file exists but there might be a schema issue. You may need to delete the file and restart.")
    
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    user_input = st.chat_input("Type your message here...")
    
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)
        
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        email_match = re.search(email_pattern, user_input)
        if email_match:
            email = email_match.group()
            if not st.session_state.get('current_email') or st.session_state.get('current_email') != email:
                st.session_state['current_email'] = email
                st.session_state['debug_log'] += f"\nExtracted email from input: {email}"
                
                if len(user_input.strip()) < 50 and email in user_input:
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
                        
                        st.session_state.messages.append({"role": "assistant", "content": response})
                        with st.chat_message("assistant"):
                            st.write(response)
                        st.stop()
        
        response = process_message(user_input, st.session_state['llm_chain'], st.session_state['llm'])
        
        st.session_state.messages.append({"role": "assistant", "content": response})
        with st.chat_message("assistant"):
            st.write(response)

if __name__ == "__main__":
    main()