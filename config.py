import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OMI_API_KEY = os.getenv("OMI_API_KEY")
OMI_APP_ID = os.getenv("OMI_APP_ID")