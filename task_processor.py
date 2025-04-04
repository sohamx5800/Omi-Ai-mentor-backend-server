from datetime import datetime, timedelta
import re

EVENT_TRIGGERS = [
    "meeting", "call", "appointment", "class", "session", "event", 
    "interview", "workshop", "conference", "seminar", "deadline", "task"
]

def detect_task(transcript):
    """Detect tasks with optional time and date from transcript."""
    transcript_lower = transcript.lower()
    for trigger in EVENT_TRIGGERS:
        if trigger in transcript_lower:
            task = f"{trigger.capitalize()} from conversation"
            time = None
            date = None

            # Extract time (e.g., "3 PM", "15:00")
            time_match = re.search(r'(\d{1,2})(?::\d{2})?\s*(am|pm)?', transcript_lower, re.IGNORECASE)
            if time_match:
                hour = int(time_match.group(1))
                period = time_match.group(2)
                if period and period.lower() == "pm" and hour != 12:
                    hour += 12
                elif period and period.lower() == "am" and hour == 12:
                    hour = 0
                time = f"{hour:02d}:00"

            # Extract date (e.g., "tomorrow", "Monday", "2025-04-04")
            date_match = re.search(r'(tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{4}-\d{2}-\d{2})', transcript_lower)
            if date_match:
                date_str = date_match.group(0)
                today = datetime.now().date()
                if date_str == "today":
                    date = today.isoformat()
                elif date_str == "tomorrow":
                    date = (today + timedelta(days=1)).isoformat()
                elif re.match(r'\d{4}-\d{2}-\d{2}', date_str):
                    date = date_str
                else:
                    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                    target_day = weekdays.index(date_str)
                    current_day = today.weekday()
                    days_ahead = (target_day - current_day + 7) % 7 or 7
                    date = (today + timedelta(days=days_ahead)).isoformat()

            return {"task": task, "time": time, "date": date}
    return None