import re
import json

def get_instructions(pizza_type):
    with open("./jsons/pizza_prep.json") as file:
        data = json.load(file)

    for key, value in data.items():
        if pizza_type in key:
            return value

def clean_text(text):
    final_txt = re.sub(r'[^a-zA-Z ]', '', text)
    final_txt = re.sub(r'\s+', ' ', final_txt).strip()
    return final_txt.upper()
