import re
import json

# ========================================================================
# TEXT UTILS
# ========================================================================

def get_instructions(pizza_type):
    with open("./jsons/pizza_prep.json") as file:
        data = json.load(file)

    for key, value in data.items():
        if pizza_type in key:
            return value
        
    # have to return an empty str so regex-cleanning-text won't crash when operating on None
    return ""

def clean_text(text):
    final_txt = re.sub(r'[^a-zA-Z ]', '', text)
    final_txt = re.sub(r'\s+', ' ', final_txt).strip()
    return final_txt.upper()
