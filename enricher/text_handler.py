import json

def get_analysis():
    with open("./jsons/pizza_analysis_lists.json") as file:
        data = json.load(file)
    return data

def get_hits(instructions, words):
    res = []
    for word in words:
        if word.upper() in instructions:
            res.append(word)
    return res
