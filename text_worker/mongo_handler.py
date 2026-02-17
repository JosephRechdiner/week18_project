from pymongo import MongoClient
import os

MONGO_URI = os.getenv("MONGO_URI") 

class MongoManger:
    client = None
    def __init__(self):
        try:
            if not MongoManger.client:
                MongoManger.client = MongoClient(MONGO_URI)
            self.client = MongoManger.client
        except Exception as e:
            raise Exception(f"Could not connect to mongo db, Error: {str(e)}")

    def get_client(self):
        return self.client  

def add_danger_field(order_id, client):
    database = client["orders_database"]
    collection = database["orders_collection"]
    try:
        collection.update_one({"order_id": order_id}, {"$set": {"allergies_flaged": True}})
    except Exception as e:
        raise Exception(f"Could not set danger field, Error: {str(e)}")
    
def add_cleaned_protocol(order_id, text, client):
    database = client["orders_database"]
    collection = database["orders_collection"]
    try:
        collection.update_one({"order_id": order_id}, {"$set": {"protocol_cleaned": text}})
    except Exception as e:
        raise Exception(f"Could not set danger field, Error: {str(e)}")
    
