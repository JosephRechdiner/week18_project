from confluent_kafka import Consumer
from mongo_handler import MongoManger, update_order_in_mongo
from redis_handler import RedisManager
import os
import json
import time

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_TOPIC = os.getenv("KAFKA_TOPIC")
BOOTSTRAP_SERVERS = os.getenv("BOOTSTRAP_SERVERS")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID")

consumer_config = {
    "bootstrap.servers": BOOTSTRAP_SERVERS,
    "group.id": KAFKA_GROUP_ID,
    "auto.offset.reset": "earliest",
    "enable.auto.commit": True
}

consumer = Consumer(consumer_config)
consumer.subscribe([KAFKA_TOPIC])

mongo_manager = MongoManger()
redis_manager = RedisManager()


while True:
    # getting data from kafka
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("❌ Error:", msg.error())
        continue
    value = msg.value().decode("utf-8")
    order = json.loads(value)
    logger.info(order)
    
    try:
        # waiting...
        time.sleep(6)
        
        # update status in mongo
        client = mongo_manager.get_client()
        update_order_in_mongo(order["order_id"], client)

        # deleting from redis
        redis_manager.r.delete(order["order_id"])



    except Exception as e:
        raise Exception(f"Error: {str(e)}")