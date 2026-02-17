from confluent_kafka import Consumer
import os
import json
import logging
from mongo_handler import MongoManger, add_prep_instructions_mongo, add_special_instructions_mongo, update_burnt_status_mongo
from text_handler import get_hits, get_analysis
from redis_handler import RedisManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_LISTEN_TOPIC = os.getenv("KAFKA_LISTEN_TOPIC")
BOOTSTRAP_SERVERS = os.getenv("BOOTSTRAP_SERVERS")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID")

consumer_config = {
    "bootstrap.servers": BOOTSTRAP_SERVERS,
    "group.id": KAFKA_GROUP_ID,
    "auto.offset.reset": "earliest",
    "enable.auto.commit": True,
}

consumer = Consumer(consumer_config)
consumer.subscribe([KAFKA_LISTEN_TOPIC])

mongo_manager = MongoManger()
redis_manager = RedisManager()

while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("❌ Error:", msg.error())
        continue
    value = msg.value().decode("utf-8")
    order = json.loads(value)
    logger.info(order)

    # insert to mongo
    client = mongo_manager.get_client()
    add_special_instructions_mongo(order["order_id"], order["special_instructions"], client)
    add_prep_instructions_mongo(order["order_id"], order["prep_instructions"], client)

    # checking for redis hits
    analysis = get_analysis()
    hits = redis_manager.r.get(order["pizza_type"])
    if not hits:
        hits = {}

        hits["allergens_hits"] = get_hits(order["prep_instructions"], analysis["common_allergens"])
        hits["meat_hits"] = get_hits(order["prep_instructions"], analysis["meat_ingredients"])
        hits["dairy_hits"] = get_hits(order["prep_instructions"], analysis["dairy_ingredients"])
        hits["kisher_hits"] = get_hits(order["prep_instructions"], analysis["forbidden_non_kosher"])

        redis_manager.r.set(order["pizza_type"], json.dumps(hits))

    if (hits["meat_hits"] and hits["dairy_hits"]) or not hits["kosher_hits"]:
        update_burnt_status_mongo(order["order_id"], client)