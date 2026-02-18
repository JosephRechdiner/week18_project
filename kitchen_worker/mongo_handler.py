from pymongo import MongoClient
import os

MONGO_URI = os.getenv("MONGO_URI") 

# ========================================================================
# MONGO
# ========================================================================

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
    
# ========================================================================
# DAL
# ========================================================================

def update_order_in_mongo(order_id: str, client: MongoClient):
    database = client["orders_database"]
    collection = database["orders_collection"]
    try:
        collection.update_one({"order_id": order_id, "status": { "$ne": "BURNT" }}, {"$set": {"status": "DELIVERED"}})
    except Exception as e:
        raise Exception(f"Could not update order status, Error: {str(e)}")