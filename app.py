from crewai import Agent, Task, Crew, Process
from langchain.sql_database import SQLDatabase
from langchain.tools.sql_database.tool import QuerySQLDataBaseTool
from langchain.tools import tool
from datetime import datetime, timedelta
import sqlite3
import re
import os
import gradio as gr
import textwrap

# Initialize SQLite database
def init_db():
    if not os.path.exists('appointments.db'):
        conn = sqlite3.connect('appointments.db')
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            purpose TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        conn.commit()
        conn.close()
    
    return SQLDatabase.from_uri("sqlite:///appointments.db")

# Initialize database
db = init_db()

# Custom tools
@tool
def book_appointment(name: str, date: str, time: str, purpose: str = "Not specified"):
    """Book a new appointment in the database"""
    try:
        # Validate date format (YYYY-MM-DD)
        datetime.strptime(date, '%Y-%m-%d')
        
        # Validate time format (HH:MM)
        datetime.strptime(time, '%H:%M')
        
        # Check for conflicting appointments
        conn = sqlite3.connect('appointments.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM appointments WHERE date = ? AND time = ?", (date, time))
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            return f"Sorry, there's already an appointment scheduled for {date} at {time}."
        
        # Book the appointment
        cursor.execute(
            "INSERT INTO appointments (name, date, time, purpose) VALUES (?, ?, ?, ?)",
            (name, date, time, purpose)
        )
        conn.commit()
        conn.close()
        
        return f"Appointment booked successfully for {name} on {date} at {time} for {purpose}."
    except ValueError as e:
        return f"Invalid date or time format. Please use YYYY-MM-DD for date and HH:MM for time."
    except Exception as e:
        return f"Error booking appointment: {str(e)}"

@tool
def get_appointments(name: str = None, date: str = None):
    """Retrieve appointments based on name or date"""
    try:
        conn = sqlite3.connect('appointments.db')
        cursor = conn.cursor()
        
        query = "SELECT * FROM appointments WHERE 1=1"
        params = []
        
        if name:
            query += " AND name LIKE ?"
            params.append(f"%{name}%")
        
        if date:
            query += " AND date = ?"
            params.append(date)
        
        cursor.execute(query, params)
        appointments = cursor.fetchall()
        conn.close()
        
        if not appointments:
            if date and name:
                return f"No appointments found for {name} on {date}."
            elif date:
                return f"No appointments found for {date}."
            elif name:
                return f"No appointments found for {name}."
            else:
                return "No appointments found."
        
        result = "Found the following appointments:\n"
        for appt in appointments:
            result += f"- {appt[1]} on {appt[2]} at {appt[3]} for {appt[4]}\n"
        
        return result
    except Exception as e:
        return f"Error retrieving appointments: {str(e)}"

@tool
def get_next_appointment(name: str = None):
    """Get the next upcoming appointment for a user"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        conn = sqlite3.connect('appointments.db')
        cursor = conn.cursor()
        
        query = """
        SELECT * FROM appointments 
        WHERE (date > ? OR (date = ? AND time >= ?)) 
        """
        params = [today, today, datetime.now().strftime('%H:%M')]
        
        if name:
            query += " AND name LIKE ?"
            params.append(f"%{name}%")
        
        query += " ORDER BY date, time LIMIT 1"
        
        cursor.execute(query, params)
        appointment = cursor.fetchone()
        conn.close()
        
        if not appointment:
            return "No upcoming appointments found."
        
        return f"Your next appointment is on {appointment[2]} at {appointment[3]} for {appointment[4]}."
    except Exception as e:
        return f"Error retrieving next appointment: {str(e)}"

# Create the natural language understanding agent
nlp_agent = Agent(
    role="Natural Language Processor",
    goal="Extract appointment details from user messages",
    backstory="I am an expert in understanding natural language and extracting key information about appointments.",
    tools=[],
    verbose=True,
    allow_delegation=True
)

# Create the booking agent
booking_agent = Agent(
    role="Appointment Scheduler",
    goal="Book and manage appointments for users",
    backstory="I handle all appointment bookings, ensuring there are no conflicts and all information is correctly stored.",
    tools=[book_appointment, get_appointments, get_next_appointment],
    verbose=True,
    allow_delegation=False
)

# Create the retrieval agent
retrieval_agent = Agent(
    role="Appointment Retrieval Specialist",
    goal="Find and provide information about existing appointments",
    backstory="I specialize in querying the appointment database to retrieve accurate appointment information.",
    tools=[get_appointments, get_next_appointment, QuerySQLDataBaseTool(db=db)],
    verbose=True,
    allow_delegation=False
)

# Create the coordinator agent
coordinator_agent = Agent(
    role="Booking Assistant Coordinator",
    goal="Coordinate between language understanding, booking, and retrieval to provide a seamless appointment booking experience",
    backstory="I am the main interface for users, understanding their needs and delegating to specialized agents to fulfill requests.",
    tools=[],
    verbose=True,
    allow_delegation=True
)

# Create tasks for the crew
process_input_task = Task(
    description="Analyze user input to determine their intention (booking appointment, checking appointments, etc.) and extract relevant details.",
    agent=nlp_agent,
    expected_output="A structured representation of user intent and appointment details"
)

booking_task = Task(
    description="Book a new appointment with the provided details.",
    agent=booking_agent,
    expected_output="Confirmation of appointment booking or error message"
)

retrieval_task = Task(
    description="Retrieve appointment details based on user query.",
    agent=retrieval_agent,
    expected_output="Appointment details or notification that no appointments were found"
)

coordination_task = Task(
    description="Coordinate the appointment booking process by delegating to appropriate specialized agents.",
    agent=coordinator_agent,
    expected_output="Complete response to user's appointment-related query"
)

# Create the crew
appointment_crew = Crew(
    agents=[nlp_agent, booking_agent, retrieval_agent, coordinator_agent],
    tasks=[process_input_task, booking_task, retrieval_task, coordination_task],
    process=Process.sequential,
    verbose=2
)

# Helper function to extract appointment details
def extract_appointment_details(message):
    name_pattern = r"(?:for|name(?:\s+is)?:?)\s+([A-Za-z\s]+)"
    date_pattern = r"(?:on|for|date:?)\s+(\d{4}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?),?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})"
    time_pattern = r"(?:at|time:?)\s+(\d{1,2}:\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm))"
    purpose_pattern = r"(?:for|purpose:?|regarding:?|about:?)\s+([^,.]+)"
    
    # Extract name
    name_match = re.search(name_pattern, message, re.IGNORECASE)
    name = name_match.group(1).strip() if name_match else "Unknown"
    
    # Extract date
    date_match = re.search(date_pattern, message, re.IGNORECASE)
    date_str = None
    if date_match:
        date_str = date_match.group(1).strip()
        # Convert date to YYYY-MM-DD format if necessary
        if re.match(r'\d{1,2}/\d{1,2}/\d{2,4}', date_str):
            parts = date_str.split('/')
            if len(parts[2]) == 2:
                parts[2] = '20' + parts[2]
            date_str = f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
    else:
        # Check for relative dates like "tomorrow", "next Monday"
        if "tomorrow" in message.lower():
            date_str = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        elif "today" in message.lower():
            date_str = datetime.now().strftime('%Y-%m-%d')
    
    # Extract time
    time_match = re.search(time_pattern, message, re.IGNORECASE)
    time_str = None
    if time_match:
        time_str = time_match.group(1).strip()
        # Convert time to 24-hour format if necessary
        if "pm" in time_str.lower() and ":" in time_str:
            hour, minute = time_str.split(":")
            hour = int(hour) + 12 if int(hour) < 12 else int(hour)
            time_str = f"{hour}:{minute.replace('pm', '').replace('PM', '').strip()}"
        elif "am" in time_str.lower() and ":" in time_str:
            time_str = time_str.replace("am", "").replace("AM", "").strip()
    
    # Extract purpose
    purpose_match = re.search(purpose_pattern, message, re.IGNORECASE)
    purpose = purpose_match.group(1).strip() if purpose_match else "Not specified"
    
    return {
        "name": name,
        "date": date_str,
        "time": time_str,
        "purpose": purpose
    }

# Function to process user message
def process_message(message):
    # Check if it's a booking request
    booking_keywords = ["book", "schedule", "set up", "arrange", "make"]
    if any(keyword in message.lower() for keyword in booking_keywords):
        # Extract appointment details
        details = extract_appointment_details(message)
        
        # Check if we have all needed details
        missing_details = []
        if details["date"] is None:
            missing_details.append("date")
        if details["time"] is None:
            missing_details.append("time")
        
        if missing_details:
            return f"I need more information to book your appointment. Please provide: {', '.join(missing_details)}"
        
        # Book the appointment
        return book_appointment(details["name"], details["date"], details["time"], details["purpose"])
    
    # Check if it's a retrieval request
    retrieval_keywords = ["check", "find", "get", "when", "do i have", "next", "upcoming"]
    if any(keyword in message.lower() for keyword in retrieval_keywords):
        # Check if asking about next appointment
        if "next" in message.lower() or "upcoming" in message.lower():
            name = None
            name_match = re.search(r"for\s+([A-Za-z\s]+)", message, re.IGNORECASE)
            if name_match:
                name = name_match.group(1).strip()
            return get_next_appointment(name)
        
        # Extract date and name for retrieval
        details = extract_appointment_details(message)
        return get_appointments(details["name"] if details["name"] != "Unknown" else None, details["date"])
    
    # General fallback
    return "I can help you book appointments or check your existing appointments. What would you like to do?"

# Create Gradio UI
def chat_interface(message, history):
    response = process_message(message)
    return response

# Create nice theme
theme = gr.themes.Soft(
    primary_hue="blue",
    secondary_hue="indigo",
)

# Build the interface
with gr.Blocks(theme=theme, title="Appointment Booking Assistant") as demo:
    gr.Markdown("# 📅 Appointment Booking Assistant")
    gr.Markdown("I can help you book appointments and check your schedule.")
    
    chatbot = gr.Chatbot(height=400)
    msg = gr.Textbox(
        placeholder="Ask me about appointments or book a new one...",
        container=False,
        scale=7
    )
    
    with gr.Accordion("Examples", open=False):
        gr.Examples(
            examples=[
                "Book an appointment for John Doe on 2023-12-15 at 14:30 for dental checkup",
                "Do I have any appointments tomorrow?",
                "When is my next appointment?",
                "Check appointments for Sarah on 2023-12-20"
            ],
            inputs=msg
        )
    
    def user(message, history):
        return "", history + [[message, None]]
    
    def bot(history):
        message = history[-1][0]
        response = process_message(message)
        history[-1][1] = response
        return history
    
    msg.submit(user, [msg, chatbot], [msg, chatbot], queue=False).then(
        bot, chatbot, chatbot
    )
    
    gr.Markdown("""
    ## How to use this assistant:
    - **Book appointments**: "Book an appointment for [name] on [date] at [time] for [purpose]"
    - **Check your schedule**: "Do I have any appointments on [date]?" or "When is my next appointment?"
    """)

# Launch the app
if __name__ == "__main__":
    demo.launch()