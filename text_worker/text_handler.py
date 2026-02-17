import re

def check_for_danger(text, danger_words):
    for word in danger_words:
        if word in text:
            return True
    return False

def clean_text(text):
    final_txt = re.sub(r'[^a-zA-Z ]', '', text)
    final_txt = re.sub(r'\s+', ' ', final_txt).strip()
    return final_txt.upper()
