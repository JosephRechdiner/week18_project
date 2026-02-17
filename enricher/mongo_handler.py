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


def update_burnt_status_mongo(order_id: str, client: MongoClient):
    database = client["orders_database"]
    collection = database["orders_collection"]
    try:
        collection.update_one({"order_id": order_id}, {"$set": {"status": "BURNT"}})
    except Exception as e:
        raise Exception(f"Could not update order status, Error: {str(e)}") 

def add_special_instructions_mongo(order_id, text, client):
    database = client["orders_database"]
    collection = database["orders_collection"]
    try:
        collection.update_one({"order_id": order_id}, {"$set": {"special_instructions": text}})
    except Exception as e:
        raise Exception(f"Could not set special instructions field, Error: {str(e)}")
    
def add_prep_instructions_mongo(order_id, text, client):
    database = client["orders_database"]
    collection = database["orders_collection"]
    try:
        collection.update_one({"order_id": order_id}, {"$set": {"prep_instructions": text}})
    except Exception as e:
        raise Exception(f"Could not set prep instructions field, Error: {str(e)}")