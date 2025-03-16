import os
import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from langchain.chains import LLMChain

def setup_llm():
    """Set up the LLM chain for conversation with the appointment booking assistant."""
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

def format_appointment_response(data, response_type, llm, clean_response=None):
    """Format appointments data into a user-friendly response."""
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
        from src.database import get_table_structure
        
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