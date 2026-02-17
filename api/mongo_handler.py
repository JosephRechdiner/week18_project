from pymongo import MongoClient
from schemas import Order
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

def save_to_mongo(orders: list[Order], client: MongoClient):
    database = client["orders_database"]
    collection = database["orders_collection"]
    
    new_orders = []
    for order in orders:
        new_order = order.model_dump()
        new_order["status"] = "PREPARING"
        try:
            collection.insert_one(new_order)
            new_order.pop("_id")
            new_orders.append(new_order)
        except Exception as e:
            raise Exception(f"Could not insert orders to mongo db, Error: {str(e)}")
    return f"Saved to mongo", new_orders

def get_order_by_id_mongo(order_id: str, client: MongoClient):
    database = client["orders_database"]
    collection = database["orders_collection"]
    return collection.find_one({"order_id": order_id}, {"_id": 0})