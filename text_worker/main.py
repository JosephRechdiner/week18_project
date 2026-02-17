from confluent_kafka import Consumer
from mongo_handler import MongoManger, add_cleaned_protocol, add_danger_field
import os
import json
import logging
from text_handler import check_for_danger, clean_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_TOPIC = os.getenv("KAFKA_TOPIC")
BOOTSTRAP_SERVERS = os.getenv("BOOTSTRAP_SERVERS")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID")

consumer_config = {
    "bootstrap.servers": BOOTSTRAP_SERVERS,
    "group.id": KAFKA_GROUP_ID,
    "auto.offset.reset": "earliest",
    "enable.auto.commit": True,
}

consumer = Consumer(consumer_config)
consumer.subscribe([KAFKA_TOPIC])

mongo_manager = MongoManger()


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

    try:
        text = order["special_instructions"]
        client = mongo_manager.get_client()

        cleaned_text = clean_text(text)
        add_cleaned_protocol(order["order_id"], cleaned_text, client)

        danger_words = ["GLUTEN","PEANUT","ALLERGY"]
        danger_order = check_for_danger(cleaned_text, danger_words)

        if danger_order:
            add_danger_field(order["order_id"], client)

    except Exception as e:
        raise Exception(f"Error: {str(e)}")
